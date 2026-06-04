#!/usr/bin/env python3
"""Estimate car decision conclusion-flipping thresholds from a Decision IR JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def var(ir: dict[str, Any], name: str, default: float = 0.0) -> float:
    item = ir.get("variables", {}).get(name, {})
    if isinstance(item, dict) and item.get("value") is not None:
        return float(item["value"])
    return default


def thresholds(ir: dict[str, Any]) -> dict[str, Any]:
    commute_days = var(ir, "commute_days_per_month")
    current_minutes = var(ir, "current_minutes_each_way")
    car_minutes = var(ir, "car_minutes_each_way")
    non_commute_trips = var(ir, "non_commute_trips_per_month")
    non_commute_minutes_saved = var(ir, "average_non_commute_minutes_saved")
    monthly_car_cost = var(ir, "monthly_car_cost")
    current_transport_cost = var(ir, "current_transport_monthly_cost")
    value_of_time = var(ir, "value_of_time")
    comfort_value = var(ir, "comfort_value_monthly")
    optionality_value = var(ir, "optionality_value_monthly")
    margin = var(ir, "decision_margin")

    time_saved = max(0.0, commute_days * 2 * (current_minutes - car_minutes) / 60)
    time_saved += max(0.0, non_commute_trips * non_commute_minutes_saved / 60)

    non_time_value = comfort_value + optionality_value
    incremental_cost = monthly_car_cost - current_transport_cost

    break_even_incremental_cost = time_saved * value_of_time + non_time_value - margin
    break_even_monthly_car_cost = current_transport_cost + break_even_incremental_cost
    break_even_value_of_time = None
    if time_saved > 0:
        break_even_value_of_time = (incremental_cost - non_time_value + margin) / time_saved

    break_even_time_saved_hours = None
    if value_of_time > 0:
        break_even_time_saved_hours = (incremental_cost - non_time_value + margin) / value_of_time

    required_lifestyle_premium = max(0.0, incremental_cost - (time_saved * value_of_time) + margin)

    return {
        "current": {
            "monthly_time_saved_hours": round(time_saved, 2),
            "monthly_car_cost": round(monthly_car_cost, 2),
            "incremental_cost": round(incremental_cost, 2),
            "value_of_time": round(value_of_time, 2),
            "comfort_plus_optionality": round(non_time_value, 2),
        },
        "flip_conditions": {
            "break_even_monthly_car_cost": round(break_even_monthly_car_cost, 2),
            "break_even_value_of_time": round(break_even_value_of_time, 2) if break_even_value_of_time is not None else None,
            "break_even_time_saved_hours": round(break_even_time_saved_hours, 2) if break_even_time_saved_hours is not None else None,
            "required_lifestyle_premium": round(required_lifestyle_premium, 2),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate conclusion-flipping thresholds.")
    parser.add_argument("ir_json", type=Path)
    args = parser.parse_args()

    print(json.dumps(thresholds(load_json(args.ir_json)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
