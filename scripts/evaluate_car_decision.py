#!/usr/bin/env python3
"""Evaluate a car Decision IR JSON file and emit derived values plus proof state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULTS = {
    "commute_days_per_month": 0,
    "current_minutes_each_way": 0,
    "car_minutes_each_way": 0,
    "non_commute_trips_per_month": 0,
    "average_non_commute_minutes_saved": 0,
    "current_transport_monthly_cost": 0,
    "min_emergency_fund_months": 6,
    "max_car_cost_income_ratio": 0.15,
    "hard_max_car_cost_income_ratio": 0.20,
    "value_of_time": 0,
    "comfort_value_monthly": 0,
    "optionality_value_monthly": 0,
    "decision_margin": 0,
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def value(ir: dict[str, Any], name: str, default: float | None = None) -> float | None:
    variables = ir.get("variables", {})
    if name in variables and isinstance(variables[name], dict):
        raw = variables[name].get("value")
        if raw is None:
            return default
        return float(raw)
    if default is not None:
        return float(default)
    if name in DEFAULTS:
        return float(DEFAULTS[name])
    return None


def emergency_fund_months(ir: dict[str, Any]) -> float | None:
    explicit = value(ir, "emergency_fund_months_after", None)
    if explicit is not None:
        return explicit
    balance = value(ir, "emergency_fund_balance", None)
    monthly_expenses = value(ir, "monthly_required_expenses", None)
    if balance is not None and monthly_expenses and monthly_expenses > 0:
        return balance / monthly_expenses
    return None


def evidence_quality(ir: dict[str, Any], names: list[str]) -> str:
    variables = ir.get("variables", {})
    confidences = []
    weak_sources = {"guessed", "unknown"}
    has_weak_source = False
    for name in names:
        variable = variables.get(name, {})
        if isinstance(variable, dict):
            if isinstance(variable.get("confidence"), (int, float)):
                confidences.append(float(variable["confidence"]))
            if variable.get("source") in weak_sources:
                has_weak_source = True
    if has_weak_source or (confidences and min(confidences) < 0.5):
        return "weak"
    if confidences and min(confidences) >= 0.75:
        return "strong"
    return "medium"


def goal(goal_id: str, claim: str, status: str, reason: str) -> dict[str, str]:
    return {"id": goal_id, "claim": claim, "status": status, "reason": reason}


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    required = [
        "monthly_car_cost",
        "monthly_after_tax_income",
    ]
    missing = [name for name in required if value(ir, name, None) is None]
    if emergency_fund_months(ir) is None:
        missing.append("emergency_fund_months_after or emergency_fund_balance/monthly_required_expenses")

    commute_days = value(ir, "commute_days_per_month")
    current_minutes = value(ir, "current_minutes_each_way")
    car_minutes = value(ir, "car_minutes_each_way")
    non_commute_trips = value(ir, "non_commute_trips_per_month")
    non_commute_minutes_saved = value(ir, "average_non_commute_minutes_saved")
    monthly_car_cost = value(ir, "monthly_car_cost", 0)
    current_transport_cost = value(ir, "current_transport_monthly_cost")
    income = value(ir, "monthly_after_tax_income", None)
    emergency_fund = emergency_fund_months(ir)
    min_emergency = value(ir, "min_emergency_fund_months")
    max_ratio = value(ir, "max_car_cost_income_ratio")
    hard_max_ratio = value(ir, "hard_max_car_cost_income_ratio")
    value_of_time = value(ir, "value_of_time")
    comfort_value = value(ir, "comfort_value_monthly")
    optionality_value = value(ir, "optionality_value_monthly")
    margin = value(ir, "decision_margin")

    commute_time_saved = max(0.0, commute_days * 2 * (current_minutes - car_minutes) / 60)
    non_commute_time_saved = max(0.0, non_commute_trips * non_commute_minutes_saved / 60)
    total_time_saved = commute_time_saved + non_commute_time_saved
    monthly_time_value = total_time_saved * value_of_time
    incremental_car_cost = monthly_car_cost - current_transport_cost
    net_monthly_value = monthly_time_value + comfort_value + optionality_value - incremental_car_cost
    car_cost_income_ratio = (monthly_car_cost / income) if income else None

    goals = []
    if emergency_fund is None:
        goals.append(goal("G1", "cash_safety", "open", "emergency_fund_months_after is missing"))
    elif emergency_fund >= min_emergency:
        goals.append(goal("G1", "cash_safety", "closed", f"{emergency_fund:g} months >= {min_emergency:g} months"))
    else:
        goals.append(goal("G1", "cash_safety", "failed", f"{emergency_fund:g} months < {min_emergency:g} months"))

    if car_cost_income_ratio is None:
        goals.append(goal("G2", "income_affordability", "open", "monthly_after_tax_income is missing"))
    elif car_cost_income_ratio <= max_ratio:
        goals.append(goal("G2", "income_affordability", "closed", f"car cost is {car_cost_income_ratio:.1%} of after-tax income"))
    elif car_cost_income_ratio <= hard_max_ratio:
        goals.append(goal("G2", "income_affordability", "failed", f"car cost is {car_cost_income_ratio:.1%}, above {max_ratio:.0%} pressure threshold"))
    else:
        goals.append(goal("G2", "income_affordability", "failed", f"car cost is {car_cost_income_ratio:.1%}, above {hard_max_ratio:.0%} hard ceiling"))

    if net_monthly_value > margin:
        goals.append(goal("G3", "benefit_exceeds_incremental_cost", "closed", f"net monthly value is ${net_monthly_value:.0f}"))
    else:
        premium = abs(net_monthly_value - margin)
        goals.append(goal("G3", "benefit_exceeds_incremental_cost", "failed", f"needs about ${premium:.0f}/month more comfort, optionality, or time value"))

    if value(ir, "expected_need_stability_months", None) is None:
        goals.append(goal("G4", "future_need_stability", "open", "future work/location/commute stability is unknown"))
    elif value(ir, "expected_need_stability_months", 0) >= 12:
        goals.append(goal("G4", "future_need_stability", "closed", "need appears stable for at least 12 months"))
    else:
        goals.append(goal("G4", "future_need_stability", "assumption", "need stability is short or uncertain"))

    failed_hard = any(g["id"] in {"G1", "G2"} and g["status"] == "failed" for g in goals)
    open_required = bool(missing)
    evidence = evidence_quality(ir, ["monthly_car_cost", "current_minutes_each_way", "car_minutes_each_way", "value_of_time"])

    if open_required:
        status = "insufficient_evidence"
    elif failed_hard:
        status = "do_not_recommend"
    elif net_monthly_value > margin and evidence == "strong":
        status = "recommend"
    elif net_monthly_value > margin:
        status = "lean_yes"
    else:
        status = "lean_no"

    return {
        "derived_values": {
            "monthly_commute_time_saved_hours": round(commute_time_saved, 2),
            "monthly_non_commute_time_saved_hours": round(non_commute_time_saved, 2),
            "monthly_time_saved_hours": round(total_time_saved, 2),
            "monthly_time_value": round(monthly_time_value, 2),
            "incremental_car_cost": round(incremental_car_cost, 2),
            "net_monthly_value": round(net_monthly_value, 2),
            "car_cost_income_ratio": round(car_cost_income_ratio, 4) if car_cost_income_ratio is not None else None,
        },
        "proof_state": {
            "target": "buy_car_better_than_no_car",
            "goals": goals,
        },
        "recommendation": {
            "status": status,
            "evidence_quality": evidence,
            "key_dependencies": [
                "monthly_car_cost",
                "monthly_time_saved_hours",
                "value_of_time",
                "emergency_fund_months_after",
                "future_need_stability",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a car Decision IR JSON file.")
    parser.add_argument("ir_json", type=Path)
    args = parser.parse_args()

    result = evaluate(load_json(args.ir_json))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
