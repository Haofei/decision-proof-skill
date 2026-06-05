#!/usr/bin/env python3
"""Evaluate a car Decision IR JSON file and emit derived values plus proof state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.domain_shared import evidence_quality_from_variables, goal, recommendation_status  # noqa: E402


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
            return None
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

def missing_for(ir: dict[str, Any], names: list[str]) -> list[str]:
    return [name for name in names if value(ir, name, None) is None]


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    required = ["monthly_car_cost", "monthly_after_tax_income"]
    missing = missing_for(ir, required)
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
    value_of_time = value(ir, "value_of_time", None)
    comfort_value = value(ir, "comfort_value_monthly")
    optionality_value = value(ir, "optionality_value_monthly")
    margin = value(ir, "decision_margin")

    time_inputs_missing = missing_for(ir, ["commute_days_per_month", "current_minutes_each_way", "car_minutes_each_way"])
    commute_time_saved = None if time_inputs_missing else max(0.0, commute_days * 2 * (current_minutes - car_minutes) / 60)
    non_commute_missing = missing_for(ir, ["non_commute_trips_per_month", "average_non_commute_minutes_saved"])
    non_commute_time_saved = None if non_commute_missing else max(0.0, non_commute_trips * non_commute_minutes_saved / 60)
    total_time_saved = None if commute_time_saved is None or non_commute_time_saved is None else commute_time_saved + non_commute_time_saved
    monthly_time_value = None if total_time_saved is None or value_of_time is None else total_time_saved * value_of_time
    incremental_car_cost = None if monthly_car_cost is None or current_transport_cost is None else monthly_car_cost - current_transport_cost
    net_monthly_value = (
        None
        if monthly_time_value is None or incremental_car_cost is None
        else monthly_time_value + comfort_value + optionality_value - incremental_car_cost
    )
    car_cost_income_ratio = (monthly_car_cost / income) if income else None

    goals = []
    if emergency_fund is None:
        goals.append(goal("G1", "cash_safety", "open", "emergency fund months cannot be derived", ["emergency_fund_months_after", "emergency_fund_balance", "monthly_required_expenses"]))
    elif emergency_fund >= min_emergency:
        goals.append(goal("G1", "cash_safety", "closed", f"{emergency_fund:g} months >= {min_emergency:g} months", ["emergency_fund_months_after", "min_emergency_fund_months"]))
    else:
        goals.append(goal("G1", "cash_safety", "failed", f"{emergency_fund:g} months < {min_emergency:g} months", ["emergency_fund_months_after", "min_emergency_fund_months"]))

    if car_cost_income_ratio is None:
        goals.append(goal("G2", "income_affordability", "open", "monthly_after_tax_income is missing", ["monthly_car_cost", "monthly_after_tax_income"]))
    elif car_cost_income_ratio <= max_ratio:
        goals.append(goal("G2", "income_affordability", "closed", f"car cost is {car_cost_income_ratio:.1%} of after-tax income", ["monthly_car_cost", "monthly_after_tax_income", "max_car_cost_income_ratio"]))
    elif car_cost_income_ratio <= hard_max_ratio:
        goals.append(goal("G2", "income_affordability", "failed", f"car cost is {car_cost_income_ratio:.1%}, above {max_ratio:.0%} pressure threshold", ["monthly_car_cost", "monthly_after_tax_income", "max_car_cost_income_ratio"]))
    else:
        goals.append(goal("G2", "income_affordability", "failed", f"car cost is {car_cost_income_ratio:.1%}, above {hard_max_ratio:.0%} hard ceiling", ["monthly_car_cost", "monthly_after_tax_income", "hard_max_car_cost_income_ratio"]))

    if net_monthly_value is None:
        open_deps = []
        if value_of_time is None:
            open_deps.append("value_of_time")
        open_deps.extend(time_inputs_missing)
        open_deps.extend(non_commute_missing)
        goals.append(goal("G3", "benefit_exceeds_incremental_cost", "open", "net monthly value cannot be computed without unknown variables", sorted(set(open_deps))))
    elif net_monthly_value > margin:
        goals.append(goal("G3", "benefit_exceeds_incremental_cost", "closed", f"net monthly value is ${net_monthly_value:.0f}", ["monthly_time_value", "incremental_car_cost", "comfort_value_monthly", "optionality_value_monthly"]))
    else:
        premium = abs(net_monthly_value - margin)
        goals.append(goal("G3", "benefit_exceeds_incremental_cost", "failed", f"needs about ${premium:.0f}/month more comfort, optionality, or time value", ["monthly_time_value", "incremental_car_cost", "comfort_value_monthly", "optionality_value_monthly"]))

    if value(ir, "expected_need_stability_months", None) is None:
        goals.append(goal("G4", "future_need_stability", "open", "future work/location/commute stability is unknown", ["expected_need_stability_months"]))
    elif value(ir, "expected_need_stability_months", 0) >= 12:
        goals.append(goal("G4", "future_need_stability", "closed", "need appears stable for at least 12 months", ["expected_need_stability_months"]))
    else:
        goals.append(goal("G4", "future_need_stability", "assumption", "need stability is short or uncertain", ["expected_need_stability_months"]))

    failed_hard = (emergency_fund is not None and emergency_fund < min_emergency) or (
        car_cost_income_ratio is not None and car_cost_income_ratio > hard_max_ratio
    )
    open_required = bool(missing) or any(g["id"] == "G3" and g["status"] == "open" for g in goals)
    evidence = evidence_quality_from_variables(ir, ["monthly_car_cost", "current_minutes_each_way", "car_minutes_each_way", "value_of_time"])
    status = recommendation_status(
        hard_failed=failed_hard,
        open_required=open_required,
        positive_case=net_monthly_value is not None and net_monthly_value > margin,
        evidence_quality=evidence,
    )

    return {
        "derived_values": {
            "monthly_commute_time_saved_hours": round(commute_time_saved, 2) if commute_time_saved is not None else None,
            "monthly_non_commute_time_saved_hours": round(non_commute_time_saved, 2) if non_commute_time_saved is not None else None,
            "monthly_time_saved_hours": round(total_time_saved, 2) if total_time_saved is not None else None,
            "monthly_time_value": round(monthly_time_value, 2) if monthly_time_value is not None else None,
            "incremental_car_cost": round(incremental_car_cost, 2) if incremental_car_cost is not None else None,
            "net_monthly_value": round(net_monthly_value, 2) if net_monthly_value is not None else None,
            "car_cost_income_ratio": round(car_cost_income_ratio, 4) if car_cost_income_ratio is not None else None,
        },
        "proof_state": {
            "target_claim": "buy_car_better_than_no_car",
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
