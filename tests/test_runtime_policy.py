import copy
import json
from pathlib import Path
import unittest

from book_logic import tasks
from book_logic.store import Error
from book_logic.verify import verify
import test_runtime
from test_runtime import answer


class PolicyTests(unittest.TestCase):
    setUp = test_runtime.RuntimeTests.setUp
    tearDown = test_runtime.RuntimeTests.tearDown

    def start(self):
        policy = json.loads((Path(__file__).parents[1] / "processing-policy.json").read_text())
        return tasks.plan(self.lib, self.book["book_id"], processing_policy=policy)["run_id"]

    def submission(self, packet):
        envelope = answer(self.lib, packet)
        result = envelope["result"]
        result["execution"] = {"model": packet["assigned_model"],
            "agent_id": "extractor" if packet["kind"] == "unit" else "coordinator",
            "policy_hash": packet["policy_hash"], "identity_assurance": "host_declared_unverified"}
        if packet["kind"] == "review":
            result["audits"] = []
            for tid in packet["required_review_tasks"]:
                task = self.lib.one("SELECT * FROM tasks WHERE id=?", (tid,))
                result["audits"].append({"task_id": tid, "artifact_id": task["output_id"],
                    "source_span_ids": [s["id"] for s in json.loads(task["payload"]).get("spans", [])],
                    "support_check": "Synthetic fixture checked against source.",
                    "omission_check": "Synthetic bottleneck qualification retained.",
                    "limitation_check": "No causal overstatement in fixture."})
        return envelope

    def reach_review(self, rid):
        while True:
            packet = tasks.next_task(self.lib, rid)
            if packet["kind"] == "review":
                return packet
            tasks.submit(self.lib, self.submission(packet))

    def test_role_and_policy_are_required(self):
        packet = tasks.next_task(self.lib, self.start())
        for field, value in [("model", "wrong"), ("policy_hash", "0" * 64)]:
            envelope = self.submission(packet)
            envelope["result"]["execution"][field] = value
            with self.assertRaises(Error):
                tasks.submit(self.lib, envelope)
        with self.assertRaises(Error):
            tasks.submit(self.lib, answer(self.lib, packet))

    def test_no_self_review_missing_audit_or_old_version(self):
        p = self.reach_review(self.start())
        for flaw in ("self", "missing", "old"):
            envelope = self.submission(p)
            if flaw == "self":
                envelope["result"]["execution"]["agent_id"] = "extractor"
            elif flaw == "missing":
                envelope["result"]["audits"].pop()
            else:
                envelope["result"]["audits"][0]["artifact_id"] = "old"
            with self.assertRaises(Error):
                tasks.submit(self.lib, envelope)

    def test_full_review_and_quality_are_separate_from_coverage(self):
        rid = self.start()
        p = self.reach_review(rid)
        status = tasks.status(self.lib, rid)
        self.assertEqual(status["coverage"], 1)
        self.assertEqual(status["quality"]["semantic_review_coverage"], 0)
        while "task_id" in p:
            tasks.submit(self.lib, self.submission(p))
            p = tasks.next_task(self.lib, rid)
        status = tasks.status(self.lib, rid)
        self.assertEqual(status["quality"]["semantic_review_coverage"], 1)
        self.assertEqual(status["quality"]["semantic_status"], "review_passed")
        self.assertEqual(verify(self.lib)["failures"], [])

    def test_span_omission_and_revision_invalidate_review(self):
        rid = self.start()
        p = self.reach_review(rid)
        envelope = self.submission(p)
        audit = next(a for a in envelope["result"]["audits"] if a["source_span_ids"])
        uid = audit["task_id"]
        broken = copy.deepcopy(envelope)
        next(a for a in broken["result"]["audits"] if a["task_id"] == uid)["source_span_ids"] = []
        with self.assertRaises(Error):
            tasks.submit(self.lib, broken)
        tasks.submit(self.lib, envelope)
        tasks.reopen(self.lib, uid)
        self.assertEqual(tasks.status(self.lib, rid)["quality"]["semantic_review_coverage"], 0)
        self.assertEqual(self.lib.one("SELECT state FROM tasks WHERE id=?", (p["task_id"],))["state"], "pending")

    def test_semantic_rework_budget_survives_reopen(self):
        rid = self.start()
        for attempt in range(3):
            p = self.reach_review(rid)
            envelope = self.submission(p)
            uid = next(a["task_id"] for a in envelope["result"]["audits"] if a["source_span_ids"])
            envelope["result"].update(decision="revise", findings=[{"task_id": uid, "message": "Missing causal qualification"}])
            tasks.submit(self.lib, envelope)
            if attempt < 2:
                tasks.reopen(self.lib, uid)
            else:
                with self.assertRaisesRegex(Error, "budget exhausted"):
                    tasks.reopen(self.lib, uid)


if __name__ == "__main__":
    unittest.main()
