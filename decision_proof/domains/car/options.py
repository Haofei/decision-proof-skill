"""Car multi-option evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decision_proof.core.domain_shared import (
    evidence_quality_from_records,
    goal,
    has_failed_goal,
    recommendation_status,
    round_or_none,
)

DEFAULTS = {
    "min_emergency_fund_months": 6.0,
    "max_car_cost_income_ratio": 0.15,
    "hard_max_car_cost_income_ratio": 0.20,
    "decision_margin": 0.0,
    "value_of_time": None,
    "monthly_after_tax_income": None,
}

STATUS_RANK = {
    "recommend": 5,
    "lean_yes": 4,
    "baseline": 3,
    "lean_no": 2,
    "insufficient_evidence": 1,
    "do_not_recommend": 0,
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def global_value(ir: dict[str, Any], name: str) -> float | None:
    variables = ir.get("variables", {})
    if name in variables and isinstance(variables[name], dict):
        raw = variables[name].get("value")
        return None if raw is None else float(raw)
    return DEFAULTS.get(name)


def model_value(
    option: dict[str, Any], name: str, default: float | None = None
) -> float | None:
    model = option.get("model", {})
    if name not in model:
        return default
    raw = model[name]
    return None if raw is None else float(raw)


def evaluate_option(ir: dict[str, Any], option: dict[str, Any]) -> dict[str, Any]:
    option_id = option.get("id")
    label = option.get("label", option_id)
    baseline = bool(option.get("baseline")) or option_id == "no_car"
    income = global_value(ir, "monthly_after_tax_income")
    value_of_time = global_value(ir, "value_of_time")
    min_emergency = global_value(ir, "min_emergency_fund_months") or 6.0
    max_ratio = global_value(ir, "max_car_cost_income_ratio") or 0.15
    hard_max_ratio = global_value(ir, "hard_max_car_cost_income_ratio") or 0.20
    margin = global_value(ir, "decision_margin") or 0.0

    monthly_cost = model_value(option, "monthly_cost", 0.0 if baseline else None)
    baseline_monthly_cost = model_value(option, "baseline_monthly_cost", 0.0)
    monthly_time_saved_hours = model_value(
        option, "monthly_time_saved_hours", 0.0 if baseline else None
    )
    comfort_value = model_value(option, "comfort_value_monthly", 0.0)
    optionality_value = model_value(option, "optionality_value_monthly", 0.0)
    emergency_fund_months_after = model_value(
        option,
        "emergency_fund_months_after",
        global_value(ir, "emergency_fund_months_after"),
    )
    stability_months = model_value(
        option,
        "expected_need_stability_months",
        global_value(ir, "expected_need_stability_months"),
    )

    goals = []
    if emergency_fund_months_after is None:
        goals.append(
            goal(
                "G1",
                "cash_safety",
                "open",
                "emergency fund after option is unknown",
                [f"{option_id}.emergency_fund_months_after"],
                severity="warning",
            )
        )
    elif emergency_fund_months_after >= min_emergency:
        goals.append(
            goal(
                "G1",
                "cash_safety",
                "closed",
                f"{emergency_fund_months_after:g} months >= {min_emergency:g} months",
                [f"{option_id}.emergency_fund_months_after"],
                severity="soft",
            )
        )
    else:
        goals.append(
            goal(
                "G1",
                "cash_safety",
                "failed",
                f"{emergency_fund_months_after:g} months < {min_emergency:g} months",
                [f"{option_id}.emergency_fund_months_after"],
                severity="hard",
            )
        )

    cost_income_ratio = None
    if monthly_cost is not None and income:
        cost_income_ratio = monthly_cost / income

    if baseline:
        goals.append(
            goal(
                "G2",
                "income_affordability",
                "closed",
                "baseline option has no additional car affordability constraint",
                [f"{option_id}.monthly_cost"],
                severity="soft",
            )
        )
    elif monthly_cost is None or income is None:
        goals.append(
            goal(
                "G2",
                "income_affordability",
                "open",
                "monthly cost or income is unknown",
                [f"{option_id}.monthly_cost", "monthly_after_tax_income"],
                severity="warning",
            )
        )
    elif cost_income_ratio <= max_ratio:
        goals.append(
            goal(
                "G2",
                "income_affordability",
                "closed",
                f"cost is {cost_income_ratio:.1%} of after-tax income",
                [f"{option_id}.monthly_cost", "monthly_after_tax_income"],
                severity="soft",
            )
        )
    elif cost_income_ratio <= hard_max_ratio:
        goals.append(
            goal(
                "G2",
                "income_affordability",
                "failed",
                f"cost is {cost_income_ratio:.1%}, above {max_ratio:.0%} pressure threshold",
                [f"{option_id}.monthly_cost", "monthly_after_tax_income"],
                severity="warning",
            )
        )
    else:
        goals.append(
            goal(
                "G2",
                "income_affordability",
                "failed",
                f"cost is {cost_income_ratio:.1%}, above {hard_max_ratio:.0%} hard ceiling",
                [f"{option_id}.monthly_cost", "monthly_after_tax_income"],
                severity="hard",
            )
        )

    incremental_cost = (
        None
        if monthly_cost is None or baseline_monthly_cost is None
        else monthly_cost - baseline_monthly_cost
    )
    monthly_time_value = (
        None
        if value_of_time is None or monthly_time_saved_hours is None
        else value_of_time * monthly_time_saved_hours
    )
    net_monthly_value = (
        None
        if incremental_cost is None or monthly_time_value is None
        else monthly_time_value + comfort_value + optionality_value - incremental_cost
    )

    if baseline:
        goals.append(
            goal(
                "G3",
                "utility_result",
                "closed",
                "baseline option is comparison anchor",
                [f"{option_id}.baseline"],
                severity="soft",
            )
        )
    elif net_monthly_value is None:
        deps = []
        if value_of_time is None:
            deps.append("value_of_time")
        if monthly_time_saved_hours is None:
            deps.append(f"{option_id}.monthly_time_saved_hours")
        if monthly_cost is None:
            deps.append(f"{option_id}.monthly_cost")
        goals.append(
            goal(
                "G3",
                "utility_result",
                "open",
                "net monthly value cannot be computed without unknown variables",
                deps,
                severity="warning",
            )
        )
    elif net_monthly_value > margin:
        goals.append(
            goal(
                "G3",
                "utility_result",
                "closed",
                f"net monthly value is ${net_monthly_value:.0f}",
                [
                    f"{option_id}.monthly_cost",
                    f"{option_id}.monthly_time_saved_hours",
                    "value_of_time",
                ],
                severity="soft",
            )
        )
    else:
        premium = abs(net_monthly_value - margin)
        goals.append(
            goal(
                "G3",
                "utility_result",
                "failed",
                f"needs about ${premium:.0f}/month more benefit to break even",
                [
                    f"{option_id}.monthly_cost",
                    f"{option_id}.monthly_time_saved_hours",
                    "value_of_time",
                ],
                severity="warning",
            )
        )

    if stability_months is None:
        goals.append(
            goal(
                "G4",
                "future_need_stability",
                "open",
                "future need stability is unknown",
                [f"{option_id}.expected_need_stability_months"],
                severity="warning",
            )
        )
    elif stability_months >= 12:
        goals.append(
            goal(
                "G4",
                "future_need_stability",
                "closed",
                "need appears stable for at least 12 months",
                [f"{option_id}.expected_need_stability_months"],
                severity="soft",
            )
        )
    else:
        goals.append(
            goal(
                "G4",
                "future_need_stability",
                "assumption",
                "need stability is short or uncertain",
                [f"{option_id}.expected_need_stability_months"],
                severity="warning",
            )
        )

    hard_failed = has_failed_goal(goals, severity="hard")
    open_required = any(
        goal_item["status"] == "open"
        for goal_item in goals
        if goal_item["id"] in {"G1", "G2", "G3"}
    )
    option_evidence = evidence_quality_from_records(option.get("evidence", {}).values())
    status = recommendation_status(
        hard_failed=hard_failed,
        open_required=open_required,
        positive_case=net_monthly_value is not None and net_monthly_value > margin,
        evidence_quality=option_evidence,
        baseline=baseline,
    )

    main_risk = None
    failed_or_open = [
        goal_item
        for goal_item in goals
        if goal_item["status"] in {"failed", "open", "assumption"}
    ]
    if failed_or_open:
        main_risk = failed_or_open[0]["reason"]

    return {
        "id": option_id,
        "label": label,
        "status": status,
        "evidence_quality": option_evidence,
        "main_risk": main_risk,
        "derived_values": {
            "monthly_cost": round_or_none(monthly_cost),
            "incremental_cost": round_or_none(incremental_cost),
            "monthly_time_saved_hours": round_or_none(monthly_time_saved_hours),
            "monthly_time_value": round_or_none(monthly_time_value),
            "net_monthly_value": round_or_none(net_monthly_value),
            "cost_income_ratio": round_or_none(cost_income_ratio, 4),
        },
        "proof_state": {
            "target_claim": f"{option_id}_is_reasonable",
            "goals": goals,
        },
    }


def rank_key(result: dict[str, Any]) -> tuple[int, float]:
    net = result.get("derived_values", {}).get("net_monthly_value")
    return (
        STATUS_RANK.get(result.get("status"), -1),
        net if isinstance(net, (int, float)) else float("-inf"),
    )


def evaluate_options(ir: dict[str, Any]) -> dict[str, Any]:
    options = ir.get("options", [])
    option_results = [evaluate_option(ir, option) for option in options]
    ranked = sorted(option_results, key=rank_key, reverse=True)
    best_actionable = next(
        (item for item in ranked if item["status"] != "baseline"),
        ranked[0] if ranked else None,
    )
    return {
        "decision_id": ir.get("decision", {}).get("id"),
        "target_claim": "rank_car_options",
        "options": option_results,
        "ranking": [item["id"] for item in ranked],
        "recommendation": {
            "status": best_actionable["status"]
            if best_actionable
            else "insufficient_evidence",
            "best_option": best_actionable["id"] if best_actionable else None,
            "summary": f"Best actionable option is {best_actionable['label']} ({best_actionable['status']})."
            if best_actionable
            else "No actionable option available.",
        },
    }
