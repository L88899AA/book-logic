import json
from pathlib import Path
import sqlite3
from urllib.parse import quote

from .books import store_book
from .store import Error, Library, encoded, file_hash, fingerprint, initialize


def migrate(old_root, new_root):
    old_root = Path(old_root).expanduser().resolve()
    db_path = old_root / "library.sqlite"
    if not db_path.is_file():
        raise Error("Legacy library.sqlite not found", "not_found")
    old = sqlite3.connect("file:" + quote(str(db_path), safe="/") + "?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    old.execute("BEGIN")
    lib = None
    mapping, imported_cards, findings, candidates = {}, 0, [], []
    try:
        initialize(new_root)
        lib = Library(new_root, writable=True)
        with lib.transaction():
            for row in old.execute("SELECT * FROM books"):
                meta = json.loads(row["metadata"])
                source = Path(meta["pdf_path"])
                if not source.is_file() or file_hash(source) != meta["sha256"]:
                    raise Error("Legacy source missing or changed; old library preserved", "source_changed")
                pages = [{"page": p["page"], "text": p["text"], "label": None,
                          "warning": "empty_or_scanned" if not p["text"].strip() else None}
                         for p in old.execute("SELECT * FROM pages WHERE book_id=? ORDER BY page", (row["id"],))]
                metadata = {"title": meta["pdf_metadata"].get("title", source.stem),
                            "author": meta["pdf_metadata"].get("author", ""), "format": "pdf",
                            "location_kind": "pdf_physical_page", "legacy_book_id": row["id"],
                            "headings": [{"depth": t[0] - 1, "title": t[1], "page": t[2]} for t in meta.get("toc", [])]}
                result = store_book(lib, source, meta["sha256"], pages, metadata, "legacy:" + meta.get("parser", "unknown"))
                mapping[row["id"]] = result
            for path in sorted((old_root / "logic").glob("*.json")):
                for card in json.loads(path.read_text(encoding="utf-8")):
                    source = mapping.get(card["book_id"])
                    if not source:
                        raise Error("Legacy card references an unknown book", "bad_evidence")
                    aid = fingerprint(["legacy", card])
                    notes, evidence = [], []
                    for ev in card.get("evidence", []):
                        page = lib.one("SELECT text FROM pages WHERE extraction_id=? AND page=?", (source["extraction_id"], ev["pdf_page"]))
                        quote_text = ev.get("quote", "")
                        start = page["text"].find(quote_text) if quote_text else -1
                        if start < 0:
                            notes.append("unmatched_quote")
                            continue
                        if page["text"].count(quote_text) > 1:
                            notes.append("ambiguous_quote_position_requires_review")
                        evidence.append({"extraction_id": source["extraction_id"], "page": ev["pdf_page"],
                                         "start": start, "end": start + len(quote_text), "quote": quote_text,
                                         "supports": ev.get("supports", "legacy quotation")})
                    if card.get("source_sha256") != source["book_id"]:
                        notes.append("legacy_source_hash_mismatch")
                    data = {"summary": card.get("source_argument", ""), "status": "legacy_candidate",
                            "original_card": card, "migration_findings": notes}
                    lib.db.execute("INSERT INTO artifacts(id,book_id,extraction_id,revision,level,data,stale) VALUES(?,?,?,1,'legacy',?,0)",
                                   (aid, source["book_id"], source["extraction_id"], encoded(data)))
                    material = {"id": "legacy", "type": "claim", "title": card.get("title", card["id"]),
                                "text": card.get("source_argument", ""), "attribution": "author_interpretation",
                                "reasoning": card.get("logic_steps", []), "conditions": card.get("limits", []),
                                "counterpoints": [], "terms": [], "evidence": evidence, "status": "legacy_candidate"}
                    lib.db.execute("INSERT INTO materials VALUES(?,?,?,?)", (aid + ":legacy", aid, source["book_id"], encoded(material)))
                    imported_cards += 1
                    candidates.append(aid + ":legacy")
                    findings.extend({"artifact_id": aid, "finding": n} for n in notes)
        return {"books": len(mapping), "legacy_cards": imported_cards, "candidate_ids": candidates, "findings": findings,
                "book_mapping": mapping, "note": "Original parsing and old files preserved. Legacy candidates are not reading completion and are not search-indexed."}
    finally:
        if lib is not None:
            lib.close()
        old.close()
