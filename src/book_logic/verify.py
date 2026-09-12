import hashlib
import json

from .store import Error, file_hash, fingerprint
from .tasks import check_evidence, validate_result


def verify(lib):
    failures = []
    books = lib.db.execute("SELECT * FROM books").fetchall()
    for book in books:
        path = lib.root / book["stored_path"]
        if not path.is_file() or file_hash(path) != book["sha256"]:
            failures.append({"id": book["id"], "error": "stored_source_changed"})
    for extraction in lib.db.execute("SELECT * FROM extractions"):
        pages = lib.db.execute("SELECT * FROM pages WHERE extraction_id=? ORDER BY page", (extraction["id"],)).fetchall()
        if fingerprint([[p["page"], p["text"]] for p in pages]) != extraction["digest"]:
            failures.append({"id": extraction["id"], "error": "extraction_changed"})
        for page in pages:
            if hashlib.sha256(page["text"].encode()).hexdigest() != page["digest"]:
                failures.append({"id": extraction["id"], "page": page["page"], "error": "page_changed"})
    for run in lib.db.execute("SELECT * FROM runs WHERE state!='stale'"):
        ranges = {}
        for task in lib.db.execute("SELECT * FROM tasks WHERE run_id=? AND kind='unit'", (run["id"],)):
            for span in json.loads(task["payload"])["spans"]:
                ranges.setdefault(span["page"], []).append((span["start"], span["end"]))
                page = lib.one("SELECT text FROM pages WHERE extraction_id=? AND page=?", (run["extraction_id"], span["page"]))
                if page["text"][span["start"]:span["end"]] != span["text"]:
                    failures.append({"id": task["id"], "error": "unit_source_changed"})
        expected = lib.db.execute("""SELECT p.page,p.text FROM pages p JOIN sections s ON s.extraction_id=p.extraction_id
            AND p.page BETWEEN s.start_page AND s.end_page WHERE p.extraction_id=? AND s.included=1""", (run["extraction_id"],)).fetchall()
        for page in expected:
            cursor = 0
            valid = True
            for left, right in sorted(ranges.get(page["page"], [])):
                if left != cursor or right <= left:
                    valid = False
                cursor = right
            if not valid or cursor != len(page["text"]):
                failures.append({"id": run["id"], "page": page["page"], "error": "coverage_gap_or_overlap"})
    count = 0
    for material in lib.db.execute("SELECT m.*,a.extraction_id FROM materials m JOIN artifacts a ON m.artifact_id=a.id"):
        count += 1
        for ev in json.loads(material["data"]).get("evidence", []):
            try:
                check_evidence(lib, ev, material["extraction_id"])
            except Error as exc:
                failures.append({"id": material["id"], "error": exc.code})
    for task in lib.db.execute("SELECT * FROM tasks WHERE state='accepted'"):
        try:
            result = json.loads(lib.one("SELECT data FROM artifacts WHERE id=? AND stale=0", (task["output_id"],))["data"])
            validate_result(lib, dict(task), result)
        except Error as exc:
            failures.append({"id": task["id"], "error": exc.code})
    return {"books": len(books), "materials": count, "failures": failures,
            "assurance": "Deterministic consistency checks only; semantic quality requires review"}
