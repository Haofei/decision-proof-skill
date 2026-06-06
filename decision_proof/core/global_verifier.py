"""Cross-domain deterministic invariant checks for Decision Proof runs."""

from __future__ import annotations

from typing import Any

STATUS_RANK = {
    "recommend": 5,
    "lean_yes": 4,
    "baseline": 3,
    "lean_no": 2,
    "insufficient_evidence": 1,
    "do_not_recommend": 0,
}


def resolve_dependency_value(ir: dict[str, Any], dependency: str) -> Any:
    if "." not in dependency:
        variable = ir.get("variables", {}).get(dependency, {})
        if isinstance(variable, dict):
            return variable.get("value")
        return None

    option_id, field = dependency.split(".", 1)
    for option in ir.get("options", []):
        if not isinstance(option, dict) or option.get("id") != option_id:
            continue
        if field in option:
            return option.get(field)
        model = option.get("model", {})
        if isinstance(model, dict):
            return model.get(field)
    return None


def verify_run(run: dict[str, Any], *, expected_hash: str) -> dict[str, Any]:
    failed: list[dict[str, str]] = []
    passed: list[str] = []

    recommendation_status = run.get("recommendation", {}).get("status")
    goals = run.get("proof_state", {}).get("goals", [])
    hard_failed = any(
        goal.get("status") == "failed" and goal.get("severity") == "hard"
        for goal in goals
    )
    open_goals = [goal for goal in goals if goal.get("status") == "open"]

    if run.get("input_ir_hash") == expected_hash:
        passed.append("input_hash_matches_ir")
    else:
        failed.append(
            {
                "id": "input_hash_matches_ir",
                "message": "input_ir_hash does not match the canonical hash of input_ir",
            }
        )

    if not (hard_failed and recommendation_status in {"recommend", "lean_yes"}):
        passed.append("hard_fail_blocks_positive_recommendation")
    else:
        failed.append(
            {
                "id": "hard_fail_blocks_positive_recommendation",
                "message": "a severity=hard failed goal cannot coexist with recommend/lean_yes",
            }
        )

    if recommendation_status != "insufficient_evidence" or open_goals:
        passed.append("insufficient_evidence_requires_open_goal")
    else:
        failed.append(
            {
                "id": "insufficient_evidence_requires_open_goal",
                "message": "insufficient_evidence requires at least one open proof goal",
            }
        )

    derived_dependencies = run.get("derived_value_dependencies", {})
    missing_dependency_entries = [
        name
        for name in run.get("derived_values", {})
        if not derived_dependencies.get(name)
    ]
    if not missing_dependency_entries:
        passed.append("derived_values_have_dependencies")
    else:
        failed.append(
            {
                "id": "derived_values_have_dependencies",
                "message": f"missing dependency mappings for: {', '.join(sorted(missing_dependency_entries))}",
            }
        )

    dependency_failures = []
    ir = run.get("input_ir", {})
    for name, value in run.get("derived_values", {}).items():
        if not isinstance(value, (int, float)):
            continue
        for dependency in derived_dependencies.get(name, []):
            if resolve_dependency_value(ir, dependency) is None:
                dependency_failures.append(f"{name} depends on unknown {dependency}")
    if not dependency_failures:
        passed.append("unknown_variables_do_not_feed_numeric_outputs")
    else:
        failed.append(
            {
                "id": "unknown_variables_do_not_feed_numeric_outputs",
                "message": "; ".join(dependency_failures),
            }
        )

    # Every defaulted prior a numeric output depends on must be disclosed: either
    # present in the IR variables or surfaced in assumptions_used. This keeps the
    # dependency graph honest without requiring priors to be present (which would
    # false-fail whenever a default is in effect).
    assumption_map = run.get("derived_value_assumptions", {})
    disclosed_priors = run.get("assumptions_used", {})
    ir_variables = ir.get("variables", {})
    undisclosed = []
    for name, value in run.get("derived_values", {}).items():
        if not isinstance(value, (int, float)):
            continue
        for prior in assumption_map.get(name, []):
            if prior not in ir_variables and prior not in disclosed_priors:
                undisclosed.append(f"{name} relies on undisclosed prior {prior}")
    if not undisclosed:
        passed.append("numeric_outputs_disclose_assumptions")
    else:
        failed.append(
            {
                "id": "numeric_outputs_disclose_assumptions",
                "message": "; ".join(undisclosed),
            }
        )

    ranking = run.get("comparison", {}).get("ranking", [])
    options = run.get("comparison", {}).get("options", [])
    if ranking and options:
        option_status = {
            option.get("id"): option.get("status")
            for option in options
            if isinstance(option, dict)
        }
        ranking_ok = True
        last_rank = None
        for option_id in ranking:
            rank = STATUS_RANK.get(option_status.get(option_id), -1)
            if last_rank is not None and rank > last_rank:
                ranking_ok = False
                break
            last_rank = rank
        if ranking_ok:
            passed.append("option_ranking_respects_status_order")
        else:
            failed.append(
                {
                    "id": "option_ranking_respects_status_order",
                    "message": "option ranking places a lower-status option ahead of a higher-status one",
                }
            )
    else:
        passed.append("option_ranking_respects_status_order")

    return {
        "ok": not failed,
        "passed_invariants": passed,
        "failed_invariants": failed,
    }
