from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import os
import tempfile

from .store import Error, encoded, file_hash, fingerprint


def extract(path):
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pypdf
        reader = pypdf.PdfReader(path)
        if reader.is_encrypted:
            raise Error("Encrypted PDF is unsupported; supply an unlocked copy", "parse_error")
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            warning = "empty_or_scanned" if not text.strip() else None
            pages.append({"page": i + 1, "label": None, "text": text, "warning": warning})
        headings = []

        def walk(items, depth=0):
            for item in items:
                if isinstance(item, list):
                    walk(item, depth + 1)
                else:
                    number = reader.get_destination_page_number(item)
                    if number is not None and number >= 0:
                        headings.append({"title": str(item.title), "page": number + 1, "depth": depth})

        walk(reader.outline)
        metadata = {"title": str((reader.metadata or {}).get("/Title", path.stem)),
                    "author": str((reader.metadata or {}).get("/Author", "")),
                    "format": "pdf", "headings": headings, "location_kind": "pdf_physical_page"}
        return pages, metadata, "pypdf:" + pypdf.__version__
    if suffix not in (".txt", ".md", ".markdown"):
        raise Error("Supported inputs: text PDF, UTF-8 TXT, Markdown", "unsupported_format")
    text = path.read_text(encoding="utf-8-sig")
    pages = [{"page": i, "label": None, "text": line, "warning": None}
             for i, line in enumerate(text.splitlines(keepends=True), 1)]
    headings = [{"title": m.group(2), "page": i, "depth": len(m.group(1)) - 1}
                for i, line in enumerate(text.splitlines(), 1)
                if (m := re.match(r"^(#{1,6})\s+(.+?)\s*$", line))]
    return pages, {"title": path.stem, "author": "", "format": suffix[1:],
                   "headings": headings, "location_kind": "text_line"}, "utf8:1"


def store_book(lib, source, sha, pages, metadata, parser):
    bid = sha
    existing = lib.db.execute("SELECT id FROM books WHERE id=?", (bid,)).fetchone()
    if existing:
        return {"book_id": bid, "status": "already_present"}
    if not pages or not any(p["text"].strip() for p in pages):
        raise Error("No readable text; OCR is not implemented", "parse_error")
    target = lib.root / "sources" / (sha + source.suffix.lower())
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix="source-", delete=False) as dst:
            staging = Path(dst.name)
            with source.open("rb") as src:
                shutil.copyfileobj(src, dst)
        if file_hash(staging) != sha:
            raise Error("Source changed during import; staging copy retained", "source_changed")
        os.replace(staging, target)
    if file_hash(target) != sha:
        raise Error("Stored source hash mismatch", "source_changed")
    text_digest = fingerprint([[p["page"], p["text"]] for p in pages])
    eid = fingerprint([sha, parser, text_digest])
    warnings = [{"page": p["page"], "warning": p["warning"]} for p in pages if p.get("warning")]
    lib.db.execute("INSERT INTO books(id,sha256,original_path,stored_path,metadata,active_extraction) VALUES(?,?,?,?,?,?)",
                   (bid, sha, str(source), str(target.relative_to(lib.root)), encoded(metadata), eid))
    lib.db.execute("INSERT INTO extractions VALUES(?,?,?,?,?)", (eid, bid, parser, text_digest, encoded(warnings)))
    for p in pages:
        lib.db.execute("INSERT INTO pages VALUES(?,?,?,?,?,?)", (eid, p["page"], p.get("label"), p["text"],
                       hashlib.sha256(p["text"].encode()).hexdigest(), p.get("warning")))
    from .retrieval import add_document
    for p in pages:
        add_document(lib, f"page:{eid}:{p['page']}", bid, eid, "source", metadata["title"], p["text"],
                     {"extraction_id": eid, "page": p["page"], "location_kind": metadata["location_kind"]})
    return {"book_id": bid, "extraction_id": eid, "pages_or_lines": len(pages),
            "warnings": warnings, "status": "imported", "mapping_required": True}


def add(lib, path):
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise Error("Source file not found", "not_found")
    if source.stat().st_size > 200 * 1024 * 1024:
        raise Error("Input exceeds the v0.1 200 MiB limit", "parse_error")
    sha = file_hash(source)
    if lib.db.execute("SELECT id FROM books WHERE id=?", (sha,)).fetchone():
        return {"book_id": sha, "status": "already_present"}
    try:
        pages, metadata, parser = extract(source)
    except Error:
        raise
    except Exception as exc:
        raise Error(f"Extraction failed ({type(exc).__name__}); source preserved", "parse_error") from exc
    with lib.transaction():
        return store_book(lib, source, sha, pages, metadata, parser)


def show(lib, bid=None):
    rows = lib.db.execute("SELECT * FROM books" + (" WHERE id=?" if bid else " ORDER BY id"), (bid,) if bid else ()).fetchall()
    if bid and not rows:
        raise Error("Book not found", "not_found")
    result = []
    for row in rows:
        book = dict(row)
        book.pop("original_path")
        book.pop("stored_path")
        book["metadata"] = json.loads(book["metadata"])
        if bid:
            book["sections"] = [dict(r) for r in lib.db.execute("SELECT * FROM sections WHERE extraction_id=? ORDER BY start_page", (book["active_extraction"],))]
            book["warnings"] = json.loads(lib.one("SELECT warnings FROM extractions WHERE id=?", (book["active_extraction"],))["warnings"])
        result.append(book)
    return result


def map_book(lib, bid, items):
    book = lib.one("SELECT * FROM books WHERE id=?", (bid,))
    count = lib.one("SELECT count(*) AS n FROM pages WHERE extraction_id=?", (book["active_extraction"],))["n"]
    if not isinstance(items, list) or not items:
        raise Error("Mapping must be a nonempty list of contiguous ranges")
    cursor = 1
    allowed = {"body", "preface", "conclusion", "notes", "bibliography", "index", "blank", "other"}
    for s in items:
        if (not isinstance(s, dict) or type(s.get("start")) is not int or type(s.get("end")) is not int
                or s["start"] != cursor or s["end"] < cursor or s["end"] > count
                or s.get("kind") not in allowed or not isinstance(s.get("title"), str) or not s["title"].strip()):
            raise Error("Mapping must cover every page/line exactly once, in order, with title and kind")
        if s["kind"] not in ("body", "preface", "conclusion") and not s.get("reason"):
            raise Error("Excluded ranges require an explicit reason")
        cursor = s["end"] + 1
    if cursor != count + 1:
        raise Error("Mapping leaves an uncovered tail")
    with lib.transaction():
        lib.db.execute("DELETE FROM sections WHERE extraction_id=?", (book["active_extraction"],))
        for s in items:
            sid = fingerprint([book["active_extraction"], s])
            lib.db.execute("INSERT INTO sections VALUES(?,?,?,?,?,?,?,?)", (sid, book["active_extraction"], s["title"],
                           s["start"], s["end"], s["kind"], int(s["kind"] in ("body", "preface", "conclusion")), s.get("reason", "")))
        lib.db.execute("UPDATE books SET map_confirmed=1,map_revision=map_revision+1 WHERE id=?", (bid,))
        lib.db.execute("UPDATE runs SET state='stale' WHERE book_id=?", (bid,))
        lib.db.execute("UPDATE tasks SET state='stale' WHERE run_id IN (SELECT id FROM runs WHERE book_id=?)", (bid,))
        lib.db.execute("UPDATE artifacts SET stale=1 WHERE book_id=? AND level!='legacy'", (bid,))
    return {"book_id": bid, "sections": len(items), "map_revision": book["map_revision"] + 1}
