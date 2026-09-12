"""Small authored retrieval regression set, not a blinded quality benchmark."""
import argparse
import json
from pathlib import Path

from book_logic.retrieval import search
from book_logic.store import Library

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--library", required=True)
parser.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="keyword")
args = parser.parse_args()
queries = json.loads((Path(__file__).resolve().parents[1] / "examples/evaluation.json").read_text())
lib = Library(args.library)
try:
    details = []
    for q in queries:
        hits = search(lib, q["query"], q["keywords"], level="material", mode=args.mode, top_k=3)["hits"]
        ranks = [n for n, h in enumerate(hits, 1) if h["id"].endswith(":" + q["expected"])]
        details.append({"query": q["query"], "rank": ranks[0] if ranks else None})
    print(json.dumps({"fixture_only": True, "mode": args.mode, "queries": len(details),
                      "hit_at_1": sum(d["rank"] == 1 for d in details) / len(details),
                      "hit_at_3": sum(d["rank"] is not None for d in details) / len(details), "details": details}, ensure_ascii=False, indent=2))
finally:
    lib.close()
