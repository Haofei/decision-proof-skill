"""Graduate-school domain evaluator."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.domain_shared import (  # noqa: E402
    boolish,
    evidence_quality_from_variables,
    goal,
    numeric_ir_value,
    raw_variable_value,
    recommendation_status,
    text_variable_value,
)
from core.guidance import format_currency, goal_lookup  # noqa: E402


DEFAULTS = {
    "target_payback_years_low_risk": 3.0,
    "target_payback_years_medium_risk": 5.0,
    "target_payback_years_high_risk": 7.0,
}

def risk_window_years(ir: dict[str, Any], risk_tolerance: str | None) -> float | None:
    if risk_tolerance == "low":
        return numeric_ir_value(ir, "target_payback_years_low_risk", DEFAULTS["target_payback_years_low_risk"])
    if risk_tolerance == "medium":
        return numeric_ir_value(ir, "target_payback_years_medium_risk", DEFAULTS["target_payback_years_medium_risk"])
    if risk_tolerance == "high":
        return numeric_ir_value(ir, "target_payback_years_high_risk", DEFAULTS["target_payback_years_high_risk"])
    return None


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    study_years = numeric_ir_value(ir, "study_years")
    annual_cost = numeric_ir_value(ir, "annual_tuition_living_cost")
    direct_salary = numeric_ir_value(ir, "direct_work_salary")
    post_grad_salary = numeric_ir_value(ir, "post_grad_expected_salary")
    savings = numeric_ir_value(ir, "savings")
    loan_required = boolish(raw_variable_value(ir, "loan_required"))
    risk_tolerance = text_variable_value(ir, "risk_tolerance")
    risk_window = risk_window_years(ir, risk_tolerance)

    cash_cost = None if study_years is None or annual_cost is None else study_years * annual_cost
    opportunity_cost = None if study_years is None or direct_salary is None else study_years * direct_salary
    total_opportunity_cost = None if cash_cost is None or opportunity_cost is None else cash_cost + opportunity_cost
    annual_salary_premium = None if direct_salary is None or post_grad_salary is None else post_grad_salary - direct_salary
    payback_years = None
    if total_opportunity_cost is not None and annual_salary_premium is not None and annual_salary_premium > 0:
        payback_years = total_opportunity_cost / annual_salary_premium
    funding_gap = None if cash_cost is None or savings is None else max(0.0, cash_cost - savings)

    goals = []
    if annual_salary_premium is None:
        goals.append(
            goal(
                "G1",
                "salary_premium_positive",
                "open",
                "salary premium cannot be computed without current and post-grad salary",
                ["direct_work_salary", "post_grad_expected_salary"],
            )
        )
    elif annual_salary_premium > 0:
        goals.append(
            goal(
                "G1",
                "salary_premium_positive",
                "closed",
                f"annual salary premium is ${annual_salary_premium:.0f}",
                ["direct_work_salary", "post_grad_expected_salary"],
            )
        )
    else:
        goals.append(
            goal(
                "G1",
                "salary_premium_positive",
                "failed",
                f"annual salary premium is ${annual_salary_premium:.0f}",
                ["direct_work_salary", "post_grad_expected_salary"],
            )
        )

    if payback_years is None or risk_window is None:
        goals.append(
            goal(
                "G2",
                "payback_within_risk_window",
                "open",
                "payback window cannot be checked without payback years and risk tolerance",
                [
                    "study_years",
                    "annual_tuition_living_cost",
                    "direct_work_salary",
                    "post_grad_expected_salary",
                    "risk_tolerance",
                ],
            )
        )
    elif payback_years <= risk_window:
        goals.append(
            goal(
                "G2",
                "payback_within_risk_window",
                "closed",
                f"payback is {payback_years:.1f} years, inside the {risk_window:.1f}-year risk window",
                ["study_years", "annual_tuition_living_cost", "direct_work_salary", "post_grad_expected_salary", "risk_tolerance"],
            )
        )
    else:
        goals.append(
            goal(
                "G2",
                "payback_within_risk_window",
                "failed",
                f"payback is {payback_years:.1f} years, above the {risk_window:.1f}-year risk window",
                ["study_years", "annual_tuition_living_cost", "direct_work_salary", "post_grad_expected_salary", "risk_tolerance"],
            )
        )

    if funding_gap is None:
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "open",
                "funding gap cannot be computed without tuition/living cost and savings",
                ["annual_tuition_living_cost", "study_years", "savings", "loan_required"],
            )
        )
    elif funding_gap <= 0:
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "closed",
                "available savings cover the direct cash cost",
                ["annual_tuition_living_cost", "study_years", "savings"],
            )
        )
    elif loan_required is True and risk_tolerance == "low":
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "failed",
                f"requires about ${funding_gap:.0f} of debt while risk tolerance is low",
                ["annual_tuition_living_cost", "study_years", "savings", "loan_required", "risk_tolerance"],
            )
        )
    elif loan_required is True:
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "assumption",
                f"requires about ${funding_gap:.0f} of debt financing",
                ["annual_tuition_living_cost", "study_years", "savings", "loan_required"],
            )
        )
    else:
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "open",
                f"about ${funding_gap:.0f} of funding gap remains unexplained",
                ["annual_tuition_living_cost", "study_years", "savings", "loan_required"],
            )
        )

    hard_failed = any(item["id"] in {"G1", "G3"} and item["status"] == "failed" for item in goals)
    open_required = any(item["id"] in {"G1", "G2"} and item["status"] == "open" for item in goals)
    evidence = evidence_quality_from_variables(
        ir,
        ["study_years", "annual_tuition_living_cost", "direct_work_salary", "post_grad_expected_salary", "savings"],
    )
    status = recommendation_status(
        hard_failed=hard_failed,
        open_required=open_required,
        positive_case=payback_years is not None and risk_window is not None and payback_years <= risk_window,
        evidence_quality=evidence,
    )

    return {
        "derived_values": {
            "cash_cost": round(cash_cost, 2) if cash_cost is not None else None,
            "opportunity_cost": round(opportunity_cost, 2) if opportunity_cost is not None else None,
            "total_opportunity_cost": round(total_opportunity_cost, 2) if total_opportunity_cost is not None else None,
            "annual_salary_premium": round(annual_salary_premium, 2) if annual_salary_premium is not None else None,
            "payback_years_after_graduation": round(payback_years, 2) if payback_years is not None else None,
            "funding_gap": round(funding_gap, 2) if funding_gap is not None else None,
        },
        "proof_state": {
            "target_claim": "graduate_school_better_than_direct_work",
            "goals": goals,
        },
        "recommendation": {
            "status": status,
            "evidence_quality": evidence,
            "key_dependencies": [
                "study_years",
                "annual_tuition_living_cost",
                "direct_work_salary",
                "post_grad_expected_salary",
                "risk_tolerance",
            ],
        },
    }


def thresholds(ir: dict[str, Any]) -> dict[str, Any]:
    study_years = numeric_ir_value(ir, "study_years")
    annual_cost = numeric_ir_value(ir, "annual_tuition_living_cost")
    direct_salary = numeric_ir_value(ir, "direct_work_salary")
    post_grad_salary = numeric_ir_value(ir, "post_grad_expected_salary")
    savings = numeric_ir_value(ir, "savings")
    risk_tolerance = text_variable_value(ir, "risk_tolerance")
    target_payback_years = risk_window_years(ir, risk_tolerance)

    unknowns = []
    for name, value in {
        "study_years": study_years,
        "annual_tuition_living_cost": annual_cost,
        "direct_work_salary": direct_salary,
        "post_grad_expected_salary": post_grad_salary,
        "savings": savings,
        "risk_tolerance": risk_tolerance,
    }.items():
        if value is None:
            unknowns.append(name)

    cash_cost = None if study_years is None or annual_cost is None else study_years * annual_cost
    total_opportunity_cost = None if cash_cost is None or direct_salary is None or study_years is None else cash_cost + (study_years * direct_salary)
    current_salary_premium = None if direct_salary is None or post_grad_salary is None else post_grad_salary - direct_salary
    current_payback_years = None
    if total_opportunity_cost is not None and current_salary_premium is not None and current_salary_premium > 0:
        current_payback_years = total_opportunity_cost / current_salary_premium

    break_even_salary_premium = None
    if total_opportunity_cost is not None and target_payback_years is not None:
        break_even_salary_premium = total_opportunity_cost / target_payback_years
    break_even_post_grad_salary = None
    if direct_salary is not None and break_even_salary_premium is not None:
        break_even_post_grad_salary = direct_salary + break_even_salary_premium
    funding_gap = None if cash_cost is None or savings is None else max(0.0, cash_cost - savings)

    return {
        "current": {
            "target_payback_years": round(target_payback_years, 2) if target_payback_years is not None else None,
            "current_payback_years": round(current_payback_years, 2) if current_payback_years is not None else None,
            "current_salary_premium": round(current_salary_premium, 2) if current_salary_premium is not None else None,
            "funding_gap": round(funding_gap, 2) if funding_gap is not None else None,
            "unknown_variables": sorted(set(unknowns)),
        },
        "flip_conditions": {
            "break_even_salary_premium_for_risk_window": round(break_even_salary_premium, 2) if break_even_salary_premium is not None else None,
            "break_even_post_grad_salary_for_risk_window": round(break_even_post_grad_salary, 2) if break_even_post_grad_salary is not None else None,
            "required_savings_without_loan": round(cash_cost, 2) if cash_cost is not None else None,
        },
    }


def verify(ir_path: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "proof_checked": False,
        "error": "no verifier implemented for graduate_school",
        "returncode": 1,
    }


def guidance(run: dict[str, Any]) -> dict[str, str]:
    proof_state = run.get("proof_state", {})
    goal_map = goal_lookup(proof_state)
    current = run.get("sensitivity", {}).get("current", {})
    flip = run.get("sensitivity", {}).get("flip_conditions", {})
    funding_gap = current.get("funding_gap")
    break_even_post_grad_salary = flip.get("break_even_post_grad_salary_for_risk_window")
    current_payback = current.get("current_payback_years")
    target_payback = current.get("target_payback_years")

    if goal_map.get("funding_path_clear", {}).get("status") == "failed":
        next_step = "Resolve the funding path before debating softer benefits."
        if isinstance(break_even_post_grad_salary, (int, float)):
            next_step = (
                f"First check whether you can close the funding gap without debt. After that, verify whether post-grad salary can credibly reach about "
                f"{format_currency(break_even_post_grad_salary, '/year')}."
            )
        return {
            "summary": "Tilt against graduate school on the current numbers. This is mainly a funding-path problem, not a fine-tuning problem.",
            "focus": f"You still need about {format_currency(funding_gap)} of funding, and debt conflicts with your current risk stance.",
            "deprioritize": "Do not spend more time shaving small tuition or lifestyle estimates until funding path and salary upside move.",
            "next_step": next_step,
        }

    if goal_map.get("payback_within_risk_window", {}).get("status") == "failed":
        focus = "The main issue is salary upside, not minor cost noise."
        if isinstance(current_payback, (int, float)) and isinstance(target_payback, (int, float)) and isinstance(break_even_post_grad_salary, (int, float)):
            focus = (
                f"You are modeling about {current_payback:.2f} years to break even; to fit your {target_payback:.2f}-year risk window, "
                f"post-grad salary would need to reach about {format_currency(break_even_post_grad_salary, '/year')}."
            )
        return {
            "summary": "Tilt against graduate school. The decision is mostly hanging on salary upside, not on smaller spreadsheet adjustments.",
            "focus": focus,
            "deprioritize": "Do not spend more time fine-tuning small tuition or living-cost deltas until salary upside is clearer.",
            "next_step": "Get a more defensible post-grad salary range before debating softer benefits.",
        }

    if goal_map.get("salary_premium_positive", {}).get("status") == "failed":
        return {
            "summary": "Do not recommend graduate school on the current salary inputs.",
            "focus": goal_map["salary_premium_positive"].get("reason", "Post-grad salary does not currently exceed direct-work salary."),
            "deprioritize": "Do not spend more time on secondary assumptions until the salary premium itself is believable.",
            "next_step": "Validate post-grad salary upside before changing anything else.",
        }

    return {
        "summary": "The conclusion is conditional; the next useful step is to verify the few numbers that truly change payback, not to debate every variable.",
        "focus": "Salary upside and funding path remain the dominant levers in this decision.",
        "deprioritize": "Do not spread effort evenly across every estimate; start with the salary range and funding path.",
        "next_step": "Validate the post-grad salary range and the funding path before changing smaller assumptions.",
    }