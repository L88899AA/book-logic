"""Replay authored synthetic fixtures; never use this to auto-complete real books."""
import argparse
import json
from pathlib import Path

from book_logic import books, tasks
from book_logic.store import Library, initialize
from book_logic.verify import verify


CASES = {
    "Capacity and delivery": {
        "id": "capacity", "title": "局部提速不等于整体交付改善",
        "text": "虚构港口的起重机提速后，出口仍是瓶颈；卸货量与客户收到货物不是同一指标。",
        "lines": [5, 7, 9], "terms": ["瓶颈", "交付", "capacity", "crane", "gate", "delivery"],
        "conditions": ["需要检查整条交付路径的约束。"],
        "counterpoints": ["出口扩容以后，更快的起重机有用；不能推出设备提速总是无效。"],
    },
    "Cash and purchasing power": {
        "id": "purchasing", "title": "名义预算增长可能伴随购买力下降",
        "text": "预算从 100 增至 120，但零件价格从 10 增至 15，可买数量从 10 降至 8。",
        "lines": [13, 15], "terms": ["预算", "购买力", "budget", "price", "parts", "purchasing"],
        "conditions": ["只比较指定零件与指定时期。"],
        "counterpoints": ["不能推广为港口所有成本均以相同比例上涨。"],
    },
    "Information and planning": {
        "id": "knowledge", "title": "参与者缺失导致操作知识未进入计划",
        "text": "夜班人员未参与，保密时刻表漏掉安全检查；邀请他们后，在原保密规则下修正了计划。",
        "lines": [19, 21], "terms": ["保密", "知识", "夜班", "confidentiality", "inspection", "operators", "planning"],
        "conditions": ["计划需要相关的一线操作知识。"],
        "counterpoints": ["修订时仍保密；不能把问题简单归因于保密。"],
    },
}


def replay(destination):
    here = Path(__file__).resolve().parent
    initialize(destination)
    lib = Library(destination, writable=True)
    try:
        book = books.add(lib, here / "harbor.md")
        books.map_book(lib, book["book_id"], json.loads((here / "harbor-map.json").read_text()))
        run = tasks.plan(lib, book["book_id"])["run_id"]
        while True:
            p = tasks.next_task(lib, run)
            if "task_id" not in p:
                break
            if p["kind"] == "unit":
                case = CASES[p["payload"]["title"]]
                evidence = [{"extraction_id": s["extraction_id"], "page": s["page"],
                             "start": s["start"], "end": s["end"], "quote": s["text"], "supports": case["title"]}
                            for s in p["payload"]["spans"] if s["page"] in case["lines"]]
                material = {k: v for k, v in case.items() if k != "lines"}
                material.update(type="case", attribution="editor_inference", evidence=evidence,
                                reasoning=[{"text": case["text"], "attribution": "editor_inference",
                                            "evidence_indices": list(range(len(evidence)))}])
                result = {"kind": "unit", "summary": case["text"], "materials": [material],
                          "coverage": [{"span_id": s["id"],
                                        "disposition": "extracted" if s["page"] in case["lines"] else "background",
                                        "note": "Authored synthetic fixture: source sentence or heading/blank line."}
                                       for s in p["payload"]["spans"]],
                          "risks": ["numbers"] if case["id"] == "purchasing" else [], "open_questions": []}
            elif p["kind"] == "review":
                result = {"kind": "review", "decision": "pass", "reviewed_task_ids": p["required_review_tasks"],
                          "findings": [], "notes": "Fixed protocol fixture; not an independent review or proof of understanding."}
            else:
                cases = list(CASES.values()) if p["kind"] == "book" else [CASES[p["payload"]["title"]]]
                materials = {json.loads(r["data"])["id"]: r["id"] for r in lib.db.execute("SELECT id,data FROM materials")}
                result = {"kind": p["kind"], "summary": "；".join(c["title"] for c in cases),
                          "question": "为什么看起来的改善未必改善最终结果？", "input_ids": [r["id"] for r in p["inputs"]],
                          "claims": [{"text": c["text"], "attribution": "editor_inference", "material_ids": [materials[c["id"]]]} for c in cases],
                          "topics": [{"term": c["title"], "material_ids": [materials[c["id"]]]} for c in cases],
                          "connections": ["三例分别检查系统约束、衡量单位、信息参与者，不能视为同一因果机制。"] if len(cases) > 1 else [],
                          "resolved_questions": [], "unresolved": []}
            tasks.submit(lib, {"schema_version": 1, "task_id": p["task_id"], "input_hash": p["input_hash"], "result": result})
        return {"fixture_only": True, "book_id": book["book_id"], "status": tasks.status(lib, run), "verification": verify(lib)}
    finally:
        lib.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, help="New empty directory")
    print(json.dumps(replay(parser.parse_args().library), ensure_ascii=False, indent=2))
