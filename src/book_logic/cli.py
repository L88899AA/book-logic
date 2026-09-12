from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .store import Error, Library, initialize


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Error(message, "arguments")


def parser():
    root = Parser(description="Local evidence-linked book processing. Generation is performed by your AI host.")
    root.add_argument("--library", default=os.environ.get("BOOK_LOGIC_LIBRARY"))
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--model-path")
    commands.add_parser("doctor")
    books = commands.add_parser("books").add_subparsers(dest="action", required=True)
    add = books.add_parser("add")
    add.add_argument("path")
    books.add_parser("list")
    show = books.add_parser("show")
    show.add_argument("book_id")
    mapping = books.add_parser("map")
    mapping.add_argument("book_id")
    mapping.add_argument("--file", required=True)
    tasks = commands.add_parser("tasks").add_subparsers(dest="action", required=True)
    tasks.add_parser("schema")
    plan = tasks.add_parser("plan")
    plan.add_argument("book_id")
    plan.add_argument("--unit-chars", type=int, default=8000)
    plan.add_argument("--context-chars", type=int, default=800)
    plan.add_argument("--policy", help="Snapshot a processing-policy JSON into the run")
    for name in ("next", "status"):
        tasks.add_parser(name).add_argument("run_id")
    submit = tasks.add_parser("submit")
    submit.add_argument("--file", required=True)
    tasks.add_parser("reopen").add_argument("task_id")
    block = tasks.add_parser("block")
    block.add_argument("task_id")
    block.add_argument("--reason", required=True)
    read = commands.add_parser("read")
    read.add_argument("--id")
    read.add_argument("--book")
    read.add_argument("--start", type=int, default=1)
    read.add_argument("--end", type=int)
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--limit", type=int, default=20)
    read.add_argument("--max-chars", type=int, default=20000)
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--keywords", default="")
    search.add_argument("--book")
    search.add_argument("--level", choices=["source", "unit", "material", "chapter", "book"])
    search.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="keyword")
    search.add_argument("--top-k", type=int, default=8)
    index = commands.add_parser("index").add_subparsers(dest="action", required=True)
    index.add_parser("build").add_argument("--model-path")
    index.add_parser("status")
    commands.add_parser("verify")
    export = commands.add_parser("materials").add_subparsers(dest="action", required=True).add_parser("export")
    export.add_argument("ids", nargs="+")
    export.add_argument("--format", choices=["json", "markdown"], default="json")
    migrate = commands.add_parser("migrate")
    migrate.add_argument("--from", dest="old_root", required=True)
    return root


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise Error("JSON input exceeds 8 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def dispatch(args):
    if args.command == "tasks" and args.action == "schema":
        from .tasks import schema
        return schema()
    if args.command == "doctor":
        db = sqlite3.connect(":memory:")
        try:
            db.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
            fts = True
        except sqlite3.OperationalError:
            fts = False
        finally:
            db.close()
        return {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version, "fts5": fts,
                "base_dependencies": {x: importlib.util.find_spec(x) is not None for x in ("pypdf", "jsonschema")},
                "semantic_installed": importlib.util.find_spec("sentence_transformers") is not None,
                "library_configured": bool(args.library),
                "library_exists": bool(args.library and (Path(args.library).expanduser() / "library.sqlite").is_file())}
    if not args.library:
        raise Error("Set --library or BOOK_LOGIC_LIBRARY", "missing_library")
    if args.command == "init":
        return initialize(args.library, args.model_path)
    if args.command == "migrate":
        from .migrate import migrate
        return migrate(args.old_root, args.library)
    writable = (args.command == "books" and args.action in ("add", "map") or
                args.command == "tasks" and args.action != "status" or args.command == "index" and args.action == "build")
    lib = Library(args.library, writable=writable)
    try:
        if args.command == "books":
            from . import books
            if args.action == "add":
                return books.add(lib, args.path)
            if args.action in ("list", "show"):
                return books.show(lib, getattr(args, "book_id", None))
            return books.map_book(lib, args.book_id, read_json(args.file))
        if args.command == "tasks":
            from . import tasks
            if args.action == "plan":
                return tasks.plan(lib, args.book_id, args.unit_chars, args.context_chars,
                                  read_json(args.policy) if args.policy else None)
            if args.action == "next":
                return tasks.next_task(lib, args.run_id)
            if args.action == "status":
                return tasks.status(lib, args.run_id)
            if args.action == "submit":
                return tasks.submit(lib, read_json(args.file))
            if args.action == "reopen":
                return tasks.reopen(lib, args.task_id)
            return tasks.block(lib, args.task_id, args.reason)
        if args.command == "read":
            from .retrieval import read
            return read(lib, args.id, args.book, args.start, args.end, args.offset, args.limit, args.max_chars)
        if args.command == "search":
            from .retrieval import search
            return search(lib, args.query, args.keywords, args.book, args.level, args.mode, args.top_k)
        if args.command == "index":
            from . import semantic
            return semantic.build(lib, args.model_path) if args.action == "build" else semantic.index_status(lib)
        if args.command == "verify":
            from .verify import verify
            return verify(lib)
        if args.command == "materials":
            from .retrieval import export_materials
            return export_materials(lib, args.ids, args.format)
    finally:
        lib.close()


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        result = dispatch(args)
        success = not (args.command == "verify" and result["failures"])
        print(json.dumps({"schema_version": 1, "ok": success, "result": result}, ensure_ascii=False, indent=2))
        return_code = 0 if success else 4
    except Error as exc:
        print(json.dumps({"schema_version": 1, "ok": False, "error": {"code": exc.code, "message": str(exc)}}, ensure_ascii=False))
        return_code = 2
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"schema_version": 1, "ok": False, "error": {"code": "runtime_error", "message": type(exc).__name__ + ": operation failed; inspect status before retrying"}}))
        return_code = 3
    if return_code:
        raise SystemExit(return_code)
