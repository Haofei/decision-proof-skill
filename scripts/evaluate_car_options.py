#!/usr/bin/env python3
"""Evaluate and rank multiple car decision options."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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


def model_value(option: dict[str, Any], name: str, default: float | None = None) -> float | None:
    model = option.get("model", {})
    if name not in model:
        return default
    raw = model[name]
    return None if raw is None else float(raw)


def evidence_quality(option: dict[str, Any]) -> str:
    evidence = option.get("evidence", {})
    confidences = []
    weak = False
    for item in evidence.values():
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        confidence = item.get("confidence")
        if source in {"unknown", "guessed"}:
            weak = True
        if isinstance(confidence, (int, float)):
            confidences.append(float(confidence))
    if weak or any(confidence < 0.5 for confidence in confidences):
        return "weak"
    if confidences and min(confidences) >= 0.75:
        return "strong"
    return "medium"


def goal(goal_id: str, claim: str, status: str, reason: str, dependencies: list[str]) -> dict[str, Any]:
    return {
        "id": goal_id,
        "claim": claim,
        "status": status,
        "reason": reason,
        "dependencies": dependencies,
    }


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
    monthly_time_saved_hours = model_value(option, "monthly_time_saved_hours", 0.0 if baseline else None)
    comfort_value = model_value(option, "comfort_value_monthly", 0.0)
    optionality_value = model_value(option, "optionality_value_monthly", 0.0)
    emergency_fund_months_after = model_value(option, "emergency_fund_months_after", global_value(ir, "emergency_fund_months_after"))
    stability_months = model_value(option, "expected_need_stability_months", global_value(ir, "expected_need_stability_months"))

    goals = []
    if emergency_fund_months_after is None:
        goals.append(goal("G1", "cash_safety", "open", "emergency fund after option is unknown", [f"{option_id}.emergency_fund_months_after"]))
    elif emergency_fund_months_after >= min_emergency:
        goals.append(goal("G1", "cash_safety", "closed", f"{emergency_fund_months_after:g} months >= {min_emergency:g} months", [f"{option_id}.emergency_fund_months_after"]))
    else:
        goals.append(goal("G1", "cash_safety", "failed", f"{emergency_fund_months_after:g} months < {min_emergency:g} months", [f"{option_id}.emergency_fund_months_after"]))

    cost_income_ratio = None
    if monthly_cost is not None and income:
        cost_income_ratio = monthly_cost / income

    if baseline:
        goals.append(goal("G2", "income_affordability", "closed", "baseline option has no additional car affordability constraint", [f"{option_id}.monthly_cost"]))
    elif monthly_cost is None or income is None:
        goals.append(goal("G2", "income_affordability", "open", "monthly cost or income is unknown", [f"{option_id}.monthly_cost", "monthly_after_tax_income"]))
    elif cost_income_ratio <= max_ratio:
        goals.append(goal("G2", "income_affordability", "closed", f"cost is {cost_income_ratio:.1%} of after-tax income", [f"{option_id}.monthly_cost", "monthly_after_tax_income"]))
    elif cost_income_ratio <= hard_max_ratio:
        goals.append(goal("G2", "income_affordability", "failed", f"cost is {cost_income_ratio:.1%}, above {max_ratio:.0%} pressure threshold", [f"{option_id}.monthly_cost", "monthly_after_tax_income"]))
    else:
        goals.append(goal("G2", "income_affordability", "failed", f"cost is {cost_income_ratio:.1%}, above {hard_max_ratio:.0%} hard ceiling", [f"{option_id}.monthly_cost", "monthly_after_tax_income"]))

    incremental_cost = None if monthly_cost is None or baseline_monthly_cost is None else monthly_cost - baseline_monthly_cost
    monthly_time_value = None if value_of_time is None or monthly_time_saved_hours is None else value_of_time * monthly_time_saved_hours
    net_monthly_value = None if incremental_cost is None or monthly_time_value is None else monthly_time_value + comfort_value + optionality_value - incremental_cost

    if baseline:
        goals.append(goal("G3", "utility_result", "closed", "baseline option is comparison anchor", [f"{option_id}.baseline"]))
    elif net_monthly_value is None:
        deps = []
        if value_of_time is None:
            deps.append("value_of_time")
        if monthly_time_saved_hours is None:
            deps.append(f"{option_id}.monthly_time_saved_hours")
        if monthly_cost is None:
            deps.append(f"{option_id}.monthly_cost")
        goals.append(goal("G3", "utility_result", "open", "net monthly value cannot be computed without unknown variables", deps))
    elif net_monthly_value > margin:
        goals.append(goal("G3", "utility_result", "closed", f"net monthly value is ${net_monthly_value:.0f}", [f"{option_id}.monthly_cost", f"{option_id}.monthly_time_saved_hours", "value_of_time"]))
    else:
        premium = abs(net_monthly_value - margin)
        goals.append(goal("G3", "utility_result", "failed", f"needs about ${premium:.0f}/month more benefit to break even", [f"{option_id}.monthly_cost", f"{option_id}.monthly_time_saved_hours", "value_of_time"]))

    if stability_months is None:
        goals.append(goal("G4", "future_need_stability", "open", "future need stability is unknown", [f"{option_id}.expected_need_stability_months"]))
    elif stability_months >= 12:
        goals.append(goal("G4", "future_need_stability", "closed", "need appears stable for at least 12 months", [f"{option_id}.expected_need_stability_months"]))
    else:
        goals.append(goal("G4", "future_need_stability", "assumption", "need stability is short or uncertain", [f"{option_id}.expected_need_stability_months"]))

    hard_failed = any(goal_item["id"] in {"G1", "G2"} and goal_item["status"] == "failed" for goal_item in goals)
    open_required = any(goal_item["status"] == "open" for goal_item in goals if goal_item["id"] in {"G1", "G2", "G3"})
    option_evidence = evidence_quality(option)

    if baseline:
        status = "baseline"
    elif hard_failed:
        status = "do_not_recommend"
    elif open_required:
        status = "insufficient_evidence"
    elif net_monthly_value is not None and net_monthly_value > margin and option_evidence == "strong":
        status = "recommend"
    elif net_monthly_value is not None and net_monthly_value > margin:
        status = "lean_yes"
    else:
        status = "lean_no"

    main_risk = None
    failed_or_open = [goal_item for goal_item in goals if goal_item["status"] in {"failed", "open", "assumption"}]
    if failed_or_open:
        main_risk = failed_or_open[0]["reason"]

    return {
        "id": option_id,
        "label": label,
        "status": status,
        "evidence_quality": option_evidence,
        "main_risk": main_risk,
        "derived_values": {
            "monthly_cost": round(monthly_cost, 2) if monthly_cost is not None else None,
            "incremental_cost": round(incremental_cost, 2) if incremental_cost is not None else None,
            "monthly_time_saved_hours": round(monthly_time_saved_hours, 2) if monthly_time_saved_hours is not None else None,
            "monthly_time_value": round(monthly_time_value, 2) if monthly_time_value is not None else None,
            "net_monthly_value": round(net_monthly_value, 2) if net_monthly_value is not None else None,
            "cost_income_ratio": round(cost_income_ratio, 4) if cost_income_ratio is not None else None,
        },
        "proof_state": {
            "target_claim": f"{option_id}_is_reasonable",
            "goals": goals,
        },
    }


def rank_key(result: dict[str, Any]) -> tuple[int, float]:
    net = result.get("derived_values", {}).get("net_monthly_value")
    return (STATUS_RANK.get(result.get("status"), -1), net if isinstance(net, (int, float)) else float("-inf"))


def evaluate_options(ir: dict[str, Any]) -> dict[str, Any]:
    options = ir.get("options", [])
    option_results = [evaluate_option(ir, option) for option in options]
    ranked = sorted(option_results, key=rank_key, reverse=True)
    best_actionable = next((item for item in ranked if item["status"] != "baseline"), ranked[0] if ranked else None)
    return {
        "decision_id": ir.get("decision", {}).get("id"),
        "target_claim": "rank_car_options",
        "options": option_results,
        "ranking": [item["id"] for item in ranked],
        "recommendation": {
            "status": best_actionable["status"] if best_actionable else "insufficient_evidence",
            "best_option": best_actionable["id"] if best_actionable else None,
            "summary": f"Best actionable option is {best_actionable['label']} ({best_actionable['status']})." if best_actionable else "No actionable option available.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate and rank multiple car options.")
    parser.add_argument("ir_json", type=Path)
    args = parser.parse_args()

    print(json.dumps(evaluate_options(load_json(args.ir_json)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
