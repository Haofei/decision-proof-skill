"""Graduate-school domain evaluator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_proof.core.domain_metadata import domain_manifest
from decision_proof.core.domain_shared import (
    applied_defaults,
    boolish,
    evidence_quality_from_variables,
    goal,
    has_failed_goal,
    numeric_ir_value,
    raw_variable_value,
    recommendation_status,
    round_or_none,
    text_variable_value,
    threshold_goal,
)
from decision_proof.core.guidance import manifest_guidance
from decision_proof.core.next_questions import manifest_next_questions
from decision_proof.core.verifier import (
    goal_hard_failed,
    hard_failed_any,
    has_open_goal,
    load_ir,
    non_negative_or_none,
    run_checks,
)

DEFAULTS = {
    "target_payback_years_low_risk": 3.0,
    "target_payback_years_medium_risk": 5.0,
    "target_payback_years_high_risk": 7.0,
}


MANIFEST = domain_manifest(Path(__file__).with_name("manifest.json"))


def risk_window_years(ir: dict[str, Any], risk_tolerance: str | None) -> float | None:
    if risk_tolerance == "low":
        return numeric_ir_value(
            ir,
            "target_payback_years_low_risk",
            DEFAULTS["target_payback_years_low_risk"],
        )
    if risk_tolerance == "medium":
        return numeric_ir_value(
            ir,
            "target_payback_years_medium_risk",
            DEFAULTS["target_payback_years_medium_risk"],
        )
    if risk_tolerance == "high":
        return numeric_ir_value(
            ir,
            "target_payback_years_high_risk",
            DEFAULTS["target_payback_years_high_risk"],
        )
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

    cash_cost = (
        None
        if study_years is None or annual_cost is None
        else study_years * annual_cost
    )
    opportunity_cost = (
        None
        if study_years is None or direct_salary is None
        else study_years * direct_salary
    )
    total_opportunity_cost = (
        None
        if cash_cost is None or opportunity_cost is None
        else cash_cost + opportunity_cost
    )
    annual_salary_premium = (
        None
        if direct_salary is None or post_grad_salary is None
        else post_grad_salary - direct_salary
    )
    payback_years = None
    if (
        total_opportunity_cost is not None
        and annual_salary_premium is not None
        and annual_salary_premium > 0
    ):
        payback_years = total_opportunity_cost / annual_salary_premium
    funding_gap = (
        None if cash_cost is None or savings is None else max(0.0, cash_cost - savings)
    )

    goals = []
    goals.append(
        threshold_goal(
            "G1",
            "salary_premium_positive",
            annual_salary_premium,
            "gt",
            0.0,
            ["direct_work_salary", "post_grad_expected_salary"],
            open_reason="salary premium cannot be computed without current and post-grad salary",
            templates={
                "closed": lambda current, limit: (
                    f"annual salary premium is ${current:.0f}"
                ),
                "failed": lambda current, limit: (
                    f"annual salary premium is ${current:.0f}"
                ),
            },
            failed_severity="hard",
        )
    )

    goals.append(
        threshold_goal(
            "G2",
            "payback_within_risk_window",
            payback_years,
            "lte",
            risk_window,
            [
                "study_years",
                "annual_tuition_living_cost",
                "direct_work_salary",
                "post_grad_expected_salary",
                "risk_tolerance",
            ],
            open_reason="payback window cannot be checked without payback years and risk tolerance",
            templates={
                "closed": lambda current, limit: (
                    f"payback is {current:.1f} years, inside the {limit:.1f}-year risk window"
                ),
                "failed": lambda current, limit: (
                    f"payback is {current:.1f} years, above the {limit:.1f}-year risk window"
                ),
            },
            failed_severity="warning",
        )
    )

    if funding_gap is None:
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "open",
                "funding gap cannot be computed without tuition/living cost and savings",
                [
                    "annual_tuition_living_cost",
                    "study_years",
                    "savings",
                    "loan_required",
                ],
                severity="warning",
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
                severity="soft",
            )
        )
    elif loan_required is True and risk_tolerance == "low":
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "failed",
                f"requires about ${funding_gap:.0f} of debt while risk tolerance is low",
                [
                    "annual_tuition_living_cost",
                    "study_years",
                    "savings",
                    "loan_required",
                    "risk_tolerance",
                ],
                severity="hard",
            )
        )
    elif loan_required is True:
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "assumption",
                f"requires about ${funding_gap:.0f} of debt financing",
                [
                    "annual_tuition_living_cost",
                    "study_years",
                    "savings",
                    "loan_required",
                ],
                severity="warning",
            )
        )
    else:
        goals.append(
            goal(
                "G3",
                "funding_path_clear",
                "open",
                f"about ${funding_gap:.0f} of funding gap remains unexplained",
                [
                    "annual_tuition_living_cost",
                    "study_years",
                    "savings",
                    "loan_required",
                ],
                severity="warning",
            )
        )

    hard_failed = has_failed_goal(goals, severity="hard")
    caution_failed = has_failed_goal(goals, severity="warning")
    open_required = any(
        item["id"] in {"G1", "G2"} and item["status"] == "open" for item in goals
    )
    evidence = evidence_quality_from_variables(
        ir,
        [
            "study_years",
            "annual_tuition_living_cost",
            "direct_work_salary",
            "post_grad_expected_salary",
            "savings",
        ],
    )
    status = recommendation_status(
        hard_failed=hard_failed,
        open_required=open_required,
        positive_case=payback_years is not None
        and risk_window is not None
        and payback_years <= risk_window,
        evidence_quality=evidence,
        caution_failed=caution_failed,
    )

    return {
        "assumptions_used": assumptions_used(ir),
        "derived_values": {
            "cash_cost": round_or_none(cash_cost),
            "opportunity_cost": round_or_none(opportunity_cost),
            "total_opportunity_cost": round_or_none(total_opportunity_cost),
            "annual_salary_premium": round_or_none(annual_salary_premium),
            "payback_years_after_graduation": round_or_none(payback_years),
            "funding_gap": round_or_none(funding_gap),
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

    cash_cost = (
        None
        if study_years is None or annual_cost is None
        else study_years * annual_cost
    )
    total_opportunity_cost = (
        None
        if cash_cost is None or direct_salary is None or study_years is None
        else cash_cost + (study_years * direct_salary)
    )
    current_salary_premium = (
        None
        if direct_salary is None or post_grad_salary is None
        else post_grad_salary - direct_salary
    )
    current_payback_years = None
    if (
        total_opportunity_cost is not None
        and current_salary_premium is not None
        and current_salary_premium > 0
    ):
        current_payback_years = total_opportunity_cost / current_salary_premium

    break_even_salary_premium = None
    if total_opportunity_cost is not None and target_payback_years is not None:
        break_even_salary_premium = total_opportunity_cost / target_payback_years
    break_even_post_grad_salary = None
    if direct_salary is not None and break_even_salary_premium is not None:
        break_even_post_grad_salary = direct_salary + break_even_salary_premium
    funding_gap = (
        None if cash_cost is None or savings is None else max(0.0, cash_cost - savings)
    )

    return {
        "current": {
            "target_payback_years": round_or_none(target_payback_years),
            "current_payback_years": round_or_none(current_payback_years),
            "current_salary_premium": round_or_none(current_salary_premium),
            "funding_gap": round_or_none(funding_gap),
            "unknown_variables": sorted(set(unknowns)),
        },
        "flip_conditions": {
            "break_even_salary_premium_for_risk_window": round_or_none(
                break_even_salary_premium
            ),
            "break_even_post_grad_salary_for_risk_window": round_or_none(
                break_even_post_grad_salary
            ),
            "required_savings_without_loan": round_or_none(cash_cost),
        },
    }


def assumptions_used(ir: dict[str, Any]) -> dict[str, float]:
    """The risk-window prior that shaped the payback comparison, if defaulted.

    Only the window for the chosen risk tolerance actually drives the result, so
    only that one is disclosed (and only when the IR did not override it).
    """
    risk_keys = {
        "low": "target_payback_years_low_risk",
        "medium": "target_payback_years_medium_risk",
        "high": "target_payback_years_high_risk",
    }
    key = risk_keys.get(text_variable_value(ir, "risk_tolerance"))
    if key is None:
        return {}
    return applied_defaults(ir, {key: DEFAULTS[key]})


def verify(ir_path: Path) -> dict[str, Any]:
    """Deterministic domain invariants (no Lean backend yet)."""
    ir = load_ir(ir_path)
    evaluation = evaluate(ir)
    sensitivity = thresholds(ir)

    status = evaluation["recommendation"]["status"]
    goals = evaluation["proof_state"]["goals"]
    derived = evaluation["derived_values"]
    flip = sensitivity["flip_conditions"]
    positive = status in {"recommend", "lean_yes"}

    payback = derived.get("payback_years_after_graduation")
    break_even_salary = flip.get("break_even_post_grad_salary_for_risk_window")

    checks = [
        (
            "salary_premium_hard_fail_blocks_positive",
            not (goal_hard_failed(goals, "salary_premium_positive") and positive),
            "a negative salary premium cannot coexist with recommend/lean_yes",
        ),
        (
            "funding_hard_fail_blocks_positive",
            not (goal_hard_failed(goals, "funding_path_clear") and positive),
            "a hard funding failure cannot coexist with recommend/lean_yes",
        ),
        (
            "do_not_recommend_requires_hard_fail",
            status != "do_not_recommend" or hard_failed_any(goals),
            "do_not_recommend must be backed by a hard-severity failed goal",
        ),
        (
            "insufficient_evidence_requires_open_goal",
            status != "insufficient_evidence" or has_open_goal(goals),
            "insufficient_evidence requires at least one open proof goal",
        ),
        (
            "payback_years_non_negative",
            non_negative_or_none(payback),
            "payback years must be non-negative or null",
        ),
        (
            "break_even_salary_non_negative",
            non_negative_or_none(break_even_salary),
            "break-even post-grad salary must be non-negative or null",
        ),
    ]
    return run_checks(
        checks,
        predicate="GraduateSchoolDeterministicInvariants",
        recommendation_status=status,
    )


def guidance(run: dict[str, Any]) -> dict[str, str]:
    return manifest_guidance(run, MANIFEST)


def next_questions(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    return manifest_next_questions(ir, run, MANIFEST)
