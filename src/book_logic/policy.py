"""Auditable host declarations, not authentication of a local AI process."""
from __future__ import annotations

import json

from .store import Error, fingerprint


def validate_policy(value):
    if not isinstance(value, dict) or set(value) != {
        "version", "models", "review_mode", "forbid_extractor_self_review",
        "max_semantic_revisions", "model_fallback",
    }:
        raise Error("Invalid processing policy", "policy_error")
    if (value["version"] != 1 or value["review_mode"] != "all"
            or value["forbid_extractor_self_review"] is not True
            or value["max_semantic_revisions"] != 2 or value["model_fallback"] != "block"):
        raise Error("Policy v1 requires full review, no self-review/fallback and two semantic revisions", "policy_error")
    models = value["models"]
    if not isinstance(models, dict) or set(models) != {"coordinator", "unit", "chapter", "book", "review"}:
        raise Error("Policy must assign every generation role", "policy_error")
    if any(not isinstance(m, str) or not m.strip() for m in models.values()):
        raise Error("Policy model names must not be empty", "policy_error")
    return value


def for_task(lib, task):
    run = lib.one("SELECT config FROM runs WHERE id=?", (task["run_id"],))
    return json.loads(run["config"]).get("processing_policy")


def validate_execution(lib, task, result):
    policy = for_task(lib, task)
    if not policy:
        return
    execution = result.get("execution")
    if not execution or execution["model"] != policy["models"][task["kind"]]:
        raise Error("Missing execution record or wrong assigned model; no silent fallback", "policy_error")
    if execution["policy_hash"] != fingerprint(policy):
        raise Error("Execution policy differs from the run snapshot", "policy_error")
    if task["kind"] != "review":
        return
    audits = result.get("audits", [])
    if len(audits) != len({a["task_id"] for a in audits}):
        raise Error("Duplicate task audit", "policy_error")
    if {a["task_id"] for a in audits} != set(result["reviewed_task_ids"]):
        raise Error("Every reviewed task needs a version-bound audit", "policy_error")
    for audit in audits:
        reviewed = lib.one("SELECT * FROM tasks WHERE id=?", (audit["task_id"],))
        if reviewed["output_id"] != audit["artifact_id"]:
            raise Error("Audit targets an obsolete artifact version", "stale_input")
        artifact = lib.one("SELECT data,stale FROM artifacts WHERE id=?", (audit["artifact_id"],))
        if artifact["stale"]:
            raise Error("Cannot audit a stale artifact", "stale_input")
        data = json.loads(artifact["data"])
        if reviewed["kind"] == "unit":
            if data.get("execution", {}).get("agent_id") == execution["agent_id"]:
                raise Error("An extractor cannot approve its own unit", "self_review")
            spans = json.loads(reviewed["payload"])["spans"]
            if set(audit["source_span_ids"]) != {s["id"] for s in spans}:
                raise Error("Full review must account for every original unit span", "incomplete_review")
        elif audit["source_span_ids"]:
            raise Error("Integration audit uses input versions, not unit span IDs", "policy_error")


def semantic_revisions(lib, task):
    count = 0
    for row in lib.db.execute("SELECT data FROM artifacts WHERE level='review' AND task_id IN (SELECT id FROM tasks WHERE run_id=?)", (task["run_id"],)):
        data = json.loads(row["data"])
        if data["decision"] == "revise" and any(f["task_id"] == task["id"] for f in data["findings"]):
            count += 1
    return count
