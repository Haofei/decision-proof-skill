"""Lean-backed verifier for the car domain."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

DEFAULTS = {
    "commute_days_per_month": 0.0,
    "current_minutes_each_way": 0.0,
    "car_minutes_each_way": 0.0,
    "non_commute_trips_per_month": 0.0,
    "average_non_commute_minutes_saved": 0.0,
    "current_transport_monthly_cost": 0.0,
    "min_emergency_fund_months": 6.0,
    "max_car_cost_income_ratio": 0.15,
    "hard_max_car_cost_income_ratio": 0.20,
    "comfort_value_monthly": 0.0,
    "optionality_value_monthly": 0.0,
    "decision_margin": 0.0,
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def var(ir: dict[str, Any], name: str, default: float | None = None) -> float | None:
    variables = ir.get("variables", {})
    if name not in variables:
        if default is not None:
            return float(default)
        if name in DEFAULTS:
            return float(DEFAULTS[name])
        return None
    item = variables.get(name, {})
    if isinstance(item, dict) and item.get("value") is not None:
        return float(item["value"])
    if isinstance(item, dict) and item.get("value") is None:
        return None
    return default


def emergency_months(ir: dict[str, Any]) -> float | None:
    explicit = var(ir, "emergency_fund_months_after", None)
    if explicit is not None:
        return explicit
    balance = var(ir, "emergency_fund_balance", None)
    monthly_expenses = var(ir, "monthly_required_expenses", None)
    if balance is not None and monthly_expenses and monthly_expenses > 0:
        return balance / monthly_expenses
    return None


def cents(amount: float) -> int:
    return int(round(amount * 100))


def nat_floor(value: float) -> int:
    return max(0, int(value // 1))


def derive(ir: dict[str, Any]) -> dict[str, Any]:
    required = [
        "monthly_car_cost",
        "monthly_after_tax_income",
        "commute_days_per_month",
        "current_minutes_each_way",
        "car_minutes_each_way",
        "value_of_time",
    ]
    missing = [name for name in required if var(ir, name, None) is None]
    if emergency_months(ir) is None:
        missing.append(
            "emergency_fund_months_after or emergency_fund_balance/monthly_required_expenses"
        )
    if missing:
        raise ValueError(f"missing variables for Lean proof: {', '.join(missing)}")

    commute_days = var(ir, "commute_days_per_month")
    current_minutes = var(ir, "current_minutes_each_way")
    car_minutes = var(ir, "car_minutes_each_way")
    non_commute_trips = var(ir, "non_commute_trips_per_month")
    non_commute_minutes_saved = var(ir, "average_non_commute_minutes_saved")
    monthly_car_cost = var(ir, "monthly_car_cost", 0.0)
    current_transport_cost = var(ir, "current_transport_monthly_cost")
    income = var(ir, "monthly_after_tax_income", 0.0)
    min_emergency = var(ir, "min_emergency_fund_months")
    hard_max_ratio = var(ir, "hard_max_car_cost_income_ratio")
    value_of_time = var(ir, "value_of_time")
    comfort_value = var(ir, "comfort_value_monthly")
    optionality_value = var(ir, "optionality_value_monthly")
    margin = var(ir, "decision_margin")

    commute_time_saved = max(
        0.0, commute_days * 2 * (current_minutes - car_minutes) / 60
    )
    non_commute_time_saved = max(
        0.0, non_commute_trips * non_commute_minutes_saved / 60
    )
    total_time_saved = commute_time_saved + non_commute_time_saved
    monthly_time_value = total_time_saved * value_of_time
    incremental_car_cost = monthly_car_cost - current_transport_cost
    net_monthly_value = (
        monthly_time_value
        + comfort_value
        + optionality_value
        - incremental_car_cost
        - margin
    )

    emergency = emergency_months(ir)
    assert emergency is not None
    hard_max_percent = int(round(hard_max_ratio * 100))

    cash_safe = nat_floor(emergency) >= nat_floor(min_emergency)
    hard_affordable = monthly_car_cost * 100 <= income * hard_max_percent
    net_positive = cents(net_monthly_value) > 0

    if not cash_safe or not hard_affordable:
        theorem = "DoNotRecommend"
        status = "do_not_recommend"
    elif net_positive:
        theorem = "LeanYes"
        status = "lean_yes"
    else:
        theorem = "LeanNo"
        status = "lean_no"

    return {
        "emergency_months": nat_floor(emergency),
        "min_emergency_months": nat_floor(min_emergency),
        "monthly_car_cost": nat_floor(monthly_car_cost),
        "monthly_income": nat_floor(income),
        "hard_max_percent": hard_max_percent,
        "net_monthly_value_cents": cents(net_monthly_value),
        "theorem": theorem,
        "status": status,
        "derived": {
            "monthly_time_saved_hours": round(total_time_saved, 2),
            "monthly_time_value": round(monthly_time_value, 2),
            "incremental_car_cost": round(incremental_car_cost, 2),
            "net_monthly_value_after_margin": round(net_monthly_value, 2),
        },
    }


def lean_int(value: int) -> str:
    return f"({value} : Int)"


def render_lean(data: dict[str, Any]) -> str:
    theorem = data["theorem"]
    return f"""-- Generated by decision_proof/domains/car/verifier.py
-- Lean checks rule closure for concrete derived values. It does not prove real-world estimates.

structure CarDecision where
  emergencyFundMonths : Nat
  minEmergencyFundMonths : Nat
  monthlyCarCost : Nat
  monthlyIncome : Nat
  hardMaxCostIncomePercent : Nat
  netMonthlyValueCents : Int

def CashSafe (d : CarDecision) : Prop :=
  d.emergencyFundMonths >= d.minEmergencyFundMonths

def HardAffordable (d : CarDecision) : Prop :=
  d.monthlyCarCost * 100 <= d.monthlyIncome * d.hardMaxCostIncomePercent

def NetPositive (d : CarDecision) : Prop :=
  d.netMonthlyValueCents > 0

def LeanYes (d : CarDecision) : Prop :=
  CashSafe d ∧ HardAffordable d ∧ NetPositive d

def LeanNo (d : CarDecision) : Prop :=
  CashSafe d ∧ HardAffordable d ∧ ¬ NetPositive d

def DoNotRecommend (d : CarDecision) : Prop :=
  ¬ CashSafe d ∨ ¬ HardAffordable d

def concreteDecision : CarDecision := {{
  emergencyFundMonths := {data["emergency_months"]},
  minEmergencyFundMonths := {data["min_emergency_months"]},
  monthlyCarCost := {data["monthly_car_cost"]},
  monthlyIncome := {data["monthly_income"]},
  hardMaxCostIncomePercent := {data["hard_max_percent"]},
  netMonthlyValueCents := {lean_int(data["net_monthly_value_cents"])}
}}

theorem decision_proof_checked : {theorem} concreteDecision := by
  unfold {theorem} CashSafe HardAffordable NetPositive concreteDecision
  native_decide
"""


def verify_ir(ir_path: Path, *, out: Path | None = None) -> dict[str, Any]:
    data = derive(load_json(ir_path))
    lean_source = render_lean(data)

    lean = shutil.which("lean")
    if not lean:
        return {
            "ok": False,
            "proof_checked": False,
            "error": "lean executable not found",
        }

    if out:
        lean_path = out
        lean_path.parent.mkdir(parents=True, exist_ok=True)
        lean_path.write_text(lean_source, encoding="utf-8")
    else:
        tempdir = Path(tempfile.mkdtemp(prefix="decision-proof-lean-"))
        lean_path = tempdir / "CarDecisionProof.lean"
        lean_path.write_text(lean_source, encoding="utf-8")

    proc = subprocess.run(
        [lean, str(lean_path)], text=True, capture_output=True, check=False
    )
    return {
        "ok": proc.returncode == 0,
        "proof_checked": proc.returncode == 0,
        "recommendation_status": data["status"],
        "proved_predicate": data["theorem"],
        "lean_file": str(lean_path),
        "derived": data["derived"],
        "lean_stdout": proc.stdout,
        "lean_stderr": proc.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and check a Lean proof for car Decision IR."
    )
    parser.add_argument("ir_json", type=Path)
    parser.add_argument("--out", type=Path, help="Path for generated .lean file")
    args = parser.parse_args()

    try:
        data = derive(load_json(args.ir_json))
        lean_source = render_lean(data)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    lean = shutil.which("lean")
    if not lean:
        print(json.dumps({"ok": False, "error": "lean executable not found"}, indent=2))
        return 1

    if args.out:
        lean_path = args.out
        lean_path.parent.mkdir(parents=True, exist_ok=True)
        lean_path.write_text(lean_source, encoding="utf-8")
    else:
        tempdir = Path(tempfile.mkdtemp(prefix="decision-proof-lean-"))
        lean_path = tempdir / "CarDecisionProof.lean"
        lean_path.write_text(lean_source, encoding="utf-8")

    proc = subprocess.run(
        [lean, str(lean_path)], text=True, capture_output=True, check=False
    )
    result = {
        "ok": proc.returncode == 0,
        "proof_checked": proc.returncode == 0,
        "recommendation_status": data["status"],
        "proved_predicate": data["theorem"],
        "lean_file": str(lean_path),
        "derived": data["derived"],
        "lean_stdout": proc.stdout,
        "lean_stderr": proc.stderr,
    }
    print(json.dumps(result, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
