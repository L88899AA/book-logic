from __future__ import annotations

import json
import re

from .store import Error, encoded, fingerprint


def terms(text):
    result = re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", text.casefold())
    for group in re.findall(r"[\u3400-\u9fff]+", text):
        result.extend(group if len(group) == 1 else [group[i:i + 2] for i in range(len(group) - 1)])
    return result


def add_document(lib, did, bid, eid, level, title, text, locator, artifact_id=None):
    lib.db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?)", (did, bid, eid, level, title, text, encoded(locator), artifact_id))
    lib.db.execute("INSERT INTO documents_fts VALUES(?,?)", (did, " ".join(terms(title + " " + text))))


def documents(lib, book_id=None, level=None):
    sql = """SELECT d.* FROM documents d JOIN books b ON d.book_id=b.id
      LEFT JOIN artifacts a ON d.artifact_id=a.id
      WHERE d.extraction_id=b.active_extraction AND (d.artifact_id IS NULL OR a.stale=0)"""
    args = []
    if book_id:
        sql += " AND d.book_id=?"
        args.append(book_id)
    if level:
        sql += " AND d.level=?"
        args.append(level)
    return [dict(r) for r in lib.db.execute(sql + " ORDER BY d.id", args)]


def document_signature(rows):
    return fingerprint([[r["id"], r["text"], r["title"], r["locator"]] for r in rows])


def search(lib, query, keywords="", book_id=None, level=None, mode="keyword", top_k=8):
    if not query.strip() or not 1 <= top_k <= 100:
        raise Error("A nonempty question and top-k in 1..100 are required")
    rows = {r["id"]: r for r in documents(lib, book_id, level)}
    lexical = []
    tokens = terms(query + " " + keywords)
    if tokens and mode != "semantic":
        expression = " OR ".join('"' + t + '"' for t in sorted(set(tokens)))
        lexical = [r[0] for r in lib.db.execute("SELECT id FROM documents_fts WHERE documents_fts MATCH ? ORDER BY bm25(documents_fts)", (expression,)) if r[0] in rows][:40]
    semantic, semantic_locations = [], {}
    if mode != "keyword":
        from .semantic import query_index
        semantic, semantic_locations = query_index(lib, query, set(rows))
    scores = {}
    for ranking in (lexical, semantic):
        for rank, did in enumerate(ranking, 1):
            scores[did] = scores.get(did, 0) + 1 / (60 + rank)
    hits = []
    for did in sorted(scores, key=scores.get, reverse=True)[:top_k]:
        r = rows[did]
        starts = [r["text"].casefold().find(t) for t in tokens]
        found = [n for n in starts if n >= 0]
        start = max(0, min(found) - 100) if found else 0
        if did in semantic_locations and did not in lexical:
            start = semantic_locations[did]["start"]
        hits.append({"id": did, "book_id": r["book_id"], "level": r["level"], "title": r["title"],
                     "snippet": r["text"][start:start + 700], "locator": json.loads(r["locator"]),
                     "keyword_rank": lexical.index(did) + 1 if did in lexical else None,
                     "semantic_rank": semantic.index(did) + 1 if did in semantic else None,
                     "rrf_score": scores[did]})
    return {"query": query, "keywords": keywords, "mode": mode, "hits": hits,
            "note": "Relative relevance only. Read full context; no score proves quality or evidence sufficiency."}


def read(lib, identifier=None, book_id=None, start=1, end=None, offset=0, limit=20, max_chars=20000):
    if offset < 0 or not 1 <= limit <= 100 or not 1 <= max_chars <= 64000:
        raise Error("Invalid read budget")
    if identifier:
        material = lib.db.execute("SELECT m.*,a.stale FROM materials m JOIN artifacts a ON m.artifact_id=a.id WHERE m.id=?", (identifier,)).fetchone()
        if material:
            if len(material["data"]) > max_chars or offset:
                return {"id": identifier, "stale": material["stale"], "data_text": material["data"][offset:offset + max_chars],
                        "next_offset": offset + max_chars if offset + max_chars < len(material["data"]) else None,
                        "encoding": "json_fragment"}
            return {**dict(material), "data": json.loads(material["data"])}
        artifact = lib.db.execute("SELECT * FROM artifacts WHERE id=?", (identifier,)).fetchone()
        if artifact:
            if len(artifact["data"]) > max_chars or offset:
                return {"id": identifier, "stale": artifact["stale"], "data_text": artifact["data"][offset:offset + max_chars],
                        "next_offset": offset + max_chars if offset + max_chars < len(artifact["data"]) else None,
                        "encoding": "json_fragment"}
            data = json.loads(artifact["data"])
            return {**dict(artifact), "data": data,
                    "material_ids": [r[0] for r in lib.db.execute("SELECT id FROM materials WHERE artifact_id=? ORDER BY id", (identifier,))]}
        task = lib.db.execute("SELECT * FROM tasks WHERE id=?", (identifier,)).fetchone()
        if task:
            from .tasks import packet
            return packet(lib, dict(task), offset, limit)
        doc = lib.db.execute("SELECT locator FROM documents WHERE id=?", (identifier,)).fetchone()
        if doc:
            locator = json.loads(doc[0])
            page = lib.one("SELECT * FROM pages WHERE extraction_id=? AND page=?", (locator["extraction_id"], locator["page"]))
            total = len(page["text"])
            page["text"] = page["text"][offset:offset + max_chars]
            page["next_offset"] = offset + max_chars if offset + max_chars < total else None
            return page
        raise Error("Material, artifact or task not found", "not_found")
    if not book_id or start < 1 or (end is not None and end < start):
        raise Error("read needs an ID or a valid book/page range")
    book = lib.one("SELECT * FROM books WHERE id=?", (book_id,))
    rows = lib.db.execute("SELECT * FROM pages WHERE extraction_id=? AND page BETWEEN ? AND ? ORDER BY page",
                          (book["active_extraction"], start, end or start)).fetchall()
    if not rows:
        raise Error("Source range not found", "not_found")
    output, used, continuation = [], 0, None
    for row in rows:
        page = dict(row)
        left = offset if page["page"] == start else 0
        piece = page["text"][left:left + max_chars - used]
        output.append({**page, "text": piece, "start": left, "end": left + len(piece)})
        used += len(piece)
        if left + len(piece) < len(page["text"]):
            continuation = {"start": page["page"], "offset": left + len(piece)}
            break
        if used == max_chars and page["page"] < (end or start):
            continuation = {"start": page["page"] + 1, "offset": 0}
            break
    return {"book_id": book_id, "location_kind": json.loads(book["metadata"])["location_kind"],
            "pages_or_lines": output, "continuation": continuation}


def export_materials(lib, ids, format="json"):
    records = []
    for mid in ids:
        if not lib.db.execute("SELECT id FROM materials WHERE id=?", (mid,)).fetchone():
            raise Error("Export accepts material IDs only", "arguments")
        item = read(lib, identifier=mid, max_chars=64000)
        if "data" not in item:
            raise Error("Material exceeds export budget; read it in pages", "budget_exceeded")
        if item.get("stale"):
            raise Error("Cannot export stale material as current", "stale_input")
        records.append(item)
    if format == "json":
        return {"materials": records, "usage": "Source-grounded writing inputs, not publication permission"}
    parts = ["# Writing materials\n"]
    for item in records:
        data = item["data"]
        parts.extend(["## " + data.get("title", item["id"]), "ID: " + item["id"],
                      data.get("text", data.get("summary", "")),
                      "Attribution: " + data.get("attribution", "integration"),
                      "Conditions: " + "; ".join(data.get("conditions", [])),
                      "Counterpoints: " + "; ".join(data.get("counterpoints", []))])
        for ev in data.get("evidence", []):
            parts.append(f"Source {item['book_id']}; extraction {ev['extraction_id']}; page/line {ev['page']}; chars {ev['start']}..{ev['end']}\n\n> " + ev["quote"].replace("\n", "\n> "))
    return {"format": "markdown", "text": "\n\n".join(parts)}
