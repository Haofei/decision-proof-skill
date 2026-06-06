"""Diff helpers for Decision Proof run artifacts."""

from __future__ import annotations

from typing import Any

from decision_proof.core.io import load_json


def flatten_variables(run: dict[str, Any]) -> dict[str, Any]:
    variables = run.get("input_ir", {}).get("variables", {})
    flattened = {}
    for name, variable in variables.items():
        if isinstance(variable, dict):
            flattened[name] = variable.get("value")
    return flattened


def changed_values(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    keys = sorted(set(before) | set(after))
    changes = {}
    for key in keys:
        if before.get(key) != after.get(key):
            changes[key] = {"from": before.get(key), "to": after.get(key)}
    return changes


def goal_map(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    goals = run.get("proof_state", {}).get("goals", [])
    return {goal.get("claim", goal.get("id")): goal for goal in goals}


def diff_runs(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_status = before.get("recommendation", {}).get("status")
    after_status = after.get("recommendation", {}).get("status")
    before_goals = goal_map(before)
    after_goals = goal_map(after)
    goal_changes = {}
    for claim in sorted(set(before_goals) | set(after_goals)):
        old = before_goals.get(claim, {})
        new = after_goals.get(claim, {})
        if old.get("status") != new.get("status") or old.get("reason") != new.get(
            "reason"
        ):
            goal_changes[claim] = {
                "status_from": old.get("status"),
                "status_to": new.get("status"),
                "reason_from": old.get("reason"),
                "reason_to": new.get("reason"),
            }

    return {
        "decision_id": after.get("decision_id") or before.get("decision_id"),
        "from_run_id": before.get("run_id"),
        "to_run_id": after.get("run_id"),
        "recommendation_change": {
            "from": before_status,
            "to": after_status,
            "changed": before_status != after_status,
        },
        "variable_changes": changed_values(
            flatten_variables(before), flatten_variables(after)
        ),
        "derived_value_changes": changed_values(
            before.get("derived_values", {}), after.get("derived_values", {})
        ),
        "proof_goal_changes": goal_changes,
        "verifier_change": {
            "from": before.get("verifier_result", {}).get("proved_predicate"),
            "to": after.get("verifier_result", {}).get("proved_predicate"),
        },
    }


def render_markdown(diff: dict[str, Any]) -> str:
    lines = [
        f"# Decision Diff: {diff.get('decision_id')}",
        "",
        "## Recommendation Change",
        "",
        f"- `{diff['recommendation_change']['from']}` -> `{diff['recommendation_change']['to']}`",
        "",
        "## Variable Changes",
        "",
    ]
    for key, change in diff["variable_changes"].items():
        lines.append(f"- `{key}`: {change['from']} -> {change['to']}")
    if not diff["variable_changes"]:
        lines.append("- No variable changes.")

    lines.extend(["", "## Derived Value Changes", ""])
    for key, change in diff["derived_value_changes"].items():
        lines.append(f"- `{key}`: {change['from']} -> {change['to']}")
    if not diff["derived_value_changes"]:
        lines.append("- No derived value changes.")

    lines.extend(["", "## Proof Goal Changes", ""])
    for claim, change in diff["proof_goal_changes"].items():
        lines.append(f"- `{claim}`: {change['status_from']} -> {change['status_to']}")
        if change.get("reason_to"):
            lines.append(f"  New reason: {change['reason_to']}")
    if not diff["proof_goal_changes"]:
        lines.append("- No proof goal changes.")

    lines.extend(
        [
            "",
            "## Verifier Change",
            "",
            f"- `{diff['verifier_change']['from']}` -> `{diff['verifier_change']['to']}`",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "changed_values",
    "diff_runs",
    "flatten_variables",
    "goal_map",
    "load_json",
    "render_markdown",
]
