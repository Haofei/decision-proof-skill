"""Shared scaffold for deterministic domain verifiers.

A domain verifier re-derives a decision from its IR and asserts a set of
invariants relating the recommendation to the proof state (e.g. a hard-failed
goal cannot coexist with a positive recommendation). This module removes the
boilerplate so each domain only declares its checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# (id, passed, message-on-failure)
Check = tuple[str, bool, str]


def load_ir(ir_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(ir_path).read_text(encoding="utf-8"))


def hard_failed_any(goals: list[dict[str, Any]]) -> bool:
    return any(
        goal.get("status") == "failed" and goal.get("severity") == "hard"
        for goal in goals
    )


def goal_hard_failed(goals: list[dict[str, Any]], claim: str) -> bool:
    for goal in goals:
        if goal.get("claim") == claim:
            return goal.get("status") == "failed" and goal.get("severity") == "hard"
    return False


def has_open_goal(goals: list[dict[str, Any]]) -> bool:
    return any(goal.get("status") == "open" for goal in goals)


def non_negative_or_none(value: Any) -> bool:
    return value is None or (isinstance(value, (int, float)) and value >= 0)


def run_checks(
    checks: list[Check],
    *,
    predicate: str,
    recommendation_status: str | None = None,
) -> dict[str, Any]:
    passed = [name for name, ok, _ in checks if ok]
    failed = [
        {"id": name, "message": message} for name, ok, message in checks if not ok
    ]
    result: dict[str, Any] = {
        "ok": not failed,
        "proof_checked": not failed,
        "proved_predicate": predicate,
        "passed_checks": passed,
        "failed_checks": failed,
    }
    if recommendation_status is not None:
        result["recommendation_status"] = recommendation_status
    return result
