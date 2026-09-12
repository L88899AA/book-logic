from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote


class Error(Exception):
    def __init__(self, message, code="invalid_input"):
        super().__init__(message)
        self.code = code


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO meta VALUES('schema','1'),('revision','0');
CREATE TABLE books(id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, original_path TEXT,
 stored_path TEXT NOT NULL, metadata TEXT NOT NULL, active_extraction TEXT,
 map_confirmed INTEGER NOT NULL DEFAULT 0, map_revision INTEGER NOT NULL DEFAULT 0);
CREATE TABLE extractions(id TEXT PRIMARY KEY,book_id TEXT NOT NULL REFERENCES books(id),
 parser TEXT NOT NULL, digest TEXT NOT NULL, warnings TEXT NOT NULL);
CREATE TABLE pages(extraction_id TEXT REFERENCES extractions(id),page INTEGER,
 label TEXT,text TEXT NOT NULL,digest TEXT NOT NULL,warning TEXT,
 PRIMARY KEY(extraction_id,page));
CREATE TABLE sections(id TEXT PRIMARY KEY,extraction_id TEXT REFERENCES extractions(id),
 title TEXT NOT NULL,start_page INTEGER NOT NULL,end_page INTEGER NOT NULL,
 kind TEXT NOT NULL,included INTEGER NOT NULL, disposition TEXT NOT NULL DEFAULT '');
CREATE TABLE runs(id TEXT PRIMARY KEY,book_id TEXT REFERENCES books(id),
 extraction_id TEXT REFERENCES extractions(id),map_revision INTEGER NOT NULL,
 config TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'active');
CREATE TABLE tasks(id TEXT PRIMARY KEY,run_id TEXT REFERENCES runs(id),kind TEXT NOT NULL,
 scope TEXT NOT NULL,sequence INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'pending',
 payload TEXT NOT NULL,input_hash TEXT,attempts INTEGER NOT NULL DEFAULT 0,
 expanded INTEGER NOT NULL DEFAULT 0,output_id TEXT,last_error TEXT);
CREATE TABLE dependencies(task_id TEXT REFERENCES tasks(id),depends_on TEXT REFERENCES tasks(id),
 PRIMARY KEY(task_id,depends_on));
CREATE TABLE artifacts(id TEXT PRIMARY KEY,task_id TEXT REFERENCES tasks(id),
 book_id TEXT REFERENCES books(id),extraction_id TEXT REFERENCES extractions(id),
 revision INTEGER NOT NULL,level TEXT NOT NULL,data TEXT NOT NULL,input_hash TEXT,
 stale INTEGER NOT NULL DEFAULT 0, UNIQUE(task_id,revision));
CREATE TABLE materials(id TEXT PRIMARY KEY,artifact_id TEXT REFERENCES artifacts(id),
 book_id TEXT REFERENCES books(id),data TEXT NOT NULL);
CREATE TABLE documents(id TEXT PRIMARY KEY,book_id TEXT NOT NULL,extraction_id TEXT NOT NULL,
 level TEXT NOT NULL,title TEXT NOT NULL,text TEXT NOT NULL,locator TEXT NOT NULL,
 artifact_id TEXT);
CREATE VIRTUAL TABLE documents_fts USING fts5(id UNINDEXED,tokens);
"""


class Library:
    def __init__(self, root, writable=False):
        self.root = Path(root).expanduser().resolve()
        path = self.root / "library.sqlite"
        if not path.is_file():
            raise Error("Library missing; run init with --library", "missing_library")
        uri = "file:" + quote(str(path), safe="/") + ("?mode=rw" if writable else "?mode=ro")
        self.db = sqlite3.connect(uri, uri=True, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        if self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] != "1":
            raise Error("Unsupported library schema", "schema_version")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        if row is None:
            raise Error("Requested record not found", "not_found")
        return dict(row)

    def revision(self):
        return int(self.one("SELECT value FROM meta WHERE key='revision'")["value"])


def initialize(root, model_path=None):
    model = Path(model_path).expanduser().resolve() if model_path else None
    if model and not model.is_dir():
        raise Error("Model directory does not exist", "missing_model")
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "library.sqlite"
    if path.exists() or any(root.iterdir()):
        raise Error("init requires an empty directory; existing data is preserved")
    db = sqlite3.connect(path)
    try:
        db.executescript(SCHEMA)
        db.execute("PRAGMA journal_mode=WAL")
        if model:
            db.execute("INSERT INTO meta VALUES('model_path',?)", (str(model),))
        db.commit()
    finally:
        db.close()
    return {"library": str(root), "schema_version": 1}
