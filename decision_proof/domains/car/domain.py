"""Car domain adapters for the Decision Proof core runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_proof.core.domain_metadata import domain_manifest
from decision_proof.core.guidance import manifest_guidance
from decision_proof.core.next_questions import (
    manifest_next_questions,
    package_questions,
    question_item,
)
from decision_proof.core.verifier import (
    goal_hard_failed,
    hard_failed_any,
    has_open_goal,
    load_ir,
    non_negative_or_none,
    run_checks,
)

from . import evaluator as evaluate_mod
from . import options as options_mod
from . import sensitivity as sensitivity_mod

MANIFEST = domain_manifest(Path(__file__).with_name("manifest.json"))


def is_option_comparison(ir: dict[str, Any]) -> bool:
    options = ir.get("options", [])
    return any(isinstance(option, dict) and "model" in option for option in options)


def normalize_option_comparison(result: dict[str, Any]) -> dict[str, Any]:
    best_option_id = result.get("recommendation", {}).get("best_option")
    best_option = next(
        (
            option
            for option in result.get("options", [])
            if option.get("id") == best_option_id
        ),
        None,
    )
    proof_state = (
        best_option.get("proof_state")
        if best_option
        else {"target_claim": result.get("target_claim"), "goals": []}
    )
    return {
        "derived_values": {
            "best_option": best_option_id,
            "best_option_net_monthly_value": best_option.get("derived_values", {}).get(
                "net_monthly_value"
            )
            if best_option
            else None,
            "best_option_cost_income_ratio": best_option.get("derived_values", {}).get(
                "cost_income_ratio"
            )
            if best_option
            else None,
            "ranking": result.get("ranking", []),
        },
        "proof_state": proof_state,
        "recommendation": result.get("recommendation", {}),
        "comparison": {
            "options": result.get("options", []),
            "ranking": result.get("ranking", []),
        },
    }


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    if is_option_comparison(ir):
        return normalize_option_comparison(options_mod.evaluate_options(ir))
    return evaluate_mod.evaluate(ir)


def thresholds(ir: dict[str, Any]) -> dict[str, Any]:
    if is_option_comparison(ir):
        return {
            "current": {
                "unsupported": "option comparison sensitivity is still script-only"
            },
            "flip_conditions": {},
        }
    return sensitivity_mod.thresholds(ir)


def verify(ir_path: Path) -> dict[str, Any]:
    """Deterministic domain invariants for a single-decision car IR."""
    ir = load_ir(ir_path)
    if is_option_comparison(ir):
        return {
            "ok": False,
            "proof_checked": False,
            "error": "verifier not implemented for car option comparison",
        }

    evaluation = evaluate(ir)
    status = evaluation["recommendation"]["status"]
    goals = evaluation["proof_state"]["goals"]
    derived = evaluation["derived_values"]
    positive = status in {"recommend", "lean_yes"}

    checks = [
        (
            "cash_safety_hard_fail_blocks_positive",
            not (goal_hard_failed(goals, "cash_safety") and positive),
            "a hard cash-safety failure cannot coexist with recommend/lean_yes",
        ),
        (
            "affordability_hard_fail_blocks_positive",
            not (goal_hard_failed(goals, "income_affordability") and positive),
            "a hard affordability failure cannot coexist with recommend/lean_yes",
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
            "car_cost_income_ratio_non_negative",
            non_negative_or_none(derived.get("car_cost_income_ratio")),
            "car_cost_income_ratio must be non-negative or null",
        ),
    ]
    return run_checks(
        checks,
        predicate="CarDeterministicInvariants",
        recommendation_status=status,
    )


def build_comparison_guidance(run: dict[str, Any]) -> dict[str, str]:
    comparison = run.get("comparison", {})
    recommendation = run.get("recommendation", {})
    best_option_id = recommendation.get("best_option")
    best_option = next(
        (
            item
            for item in comparison.get("options", [])
            if item.get("id") == best_option_id
        ),
        None,
    )
    main_risk = best_option.get("main_risk") if isinstance(best_option, dict) else None
    return {
        "summary": recommendation.get(
            "summary",
            "Use the ranking as a shortlist, not as a reason to micromanage every option.",
        ),
        "focus": main_risk
        or "Validate the main risk on the top-ranked option before over-optimizing the rest of the list.",
        "deprioritize": "Do not overfit tiny ranking differences across every option before checking the top option's main risk.",
        "next_step": "Get one stronger fact on the top-ranked option before revisiting the ranking.",
    }


def guidance(run: dict[str, Any]) -> dict[str, str]:
    if run.get("comparison", {}).get("options"):
        return build_comparison_guidance(run)
    return manifest_guidance(run, MANIFEST)


def next_questions(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    if run.get("comparison", {}).get("options"):
        comparison = run.get("comparison", {})
        recommendation = run.get("recommendation", {})
        best_option_id = recommendation.get("best_option")
        best_option = next(
            (
                item
                for item in comparison.get("options", [])
                if item.get("id") == best_option_id
            ),
            None,
        )
        items = []
        if isinstance(best_option, dict):
            items.append(
                question_item(
                    question_id=f"car.option.{best_option_id}.main_risk",
                    question=f"What is the strongest concrete evidence you can get about the main risk on {best_option.get('label', best_option_id)}?",
                    why_this_question="The top-ranked option is only as good as its main unresolved risk.",
                    expected_variable_updates=[best_option_id],
                    possible_conclusion_impact="Could confirm the current top-ranked option or reorder the shortlist.",
                    priority=90,
                )
            )
            for goal_item in best_option.get("proof_state", {}).get("goals", []):
                if (
                    goal_item.get("claim") == "income_affordability"
                    and goal_item.get("status") == "open"
                ):
                    items.append(
                        question_item(
                            question_id=f"car.option.{best_option_id}.income",
                            question="What after-tax monthly income should the comparison use right now?",
                            why_this_question="Income affordability is still open on the top-ranked option, so the ranking is not yet fully anchored.",
                            expected_variable_updates=["monthly_after_tax_income"],
                            possible_conclusion_impact="Could shift one or more options between actionable and non-actionable.",
                            priority=85,
                        )
                    )
                if (
                    goal_item.get("claim") == "utility_result"
                    and goal_item.get("status") == "open"
                ):
                    items.append(
                        question_item(
                            question_id=f"car.option.{best_option_id}.time_value",
                            question="What is one saved hour worth to you in this option comparison?",
                            why_this_question="The utility result is still open because the comparison cannot turn time savings into value yet.",
                            expected_variable_updates=["value_of_time"],
                            possible_conclusion_impact="Could flip the top-ranked option or tighten the gap between close options.",
                            priority=80,
                        )
                    )
        return package_questions(items)

    return manifest_next_questions(ir, run, MANIFEST)


def derived_value_dependencies(run: dict[str, Any]) -> dict[str, list[str]]:
    if run.get("comparison", {}).get("options"):
        best_option_id = run.get("recommendation", {}).get("best_option")
        option_ids = [
            item.get("id")
            for item in run.get("comparison", {}).get("options", [])
            if isinstance(item, dict) and item.get("id")
        ]
        option_cost_deps = [f"{option_id}.monthly_cost" for option_id in option_ids]
        mapping = {
            "best_option": option_cost_deps or [best_option_id]
            if best_option_id
            else option_cost_deps,
            "best_option_net_monthly_value": [
                f"{best_option_id}.monthly_cost",
                f"{best_option_id}.monthly_time_saved_hours",
                "value_of_time",
            ]
            if best_option_id
            else option_cost_deps,
            "best_option_cost_income_ratio": [
                f"{best_option_id}.monthly_cost",
                "monthly_after_tax_income",
            ]
            if best_option_id
            else option_cost_deps,
            "ranking": option_cost_deps,
        }
        return {key: value for key, value in mapping.items() if value}

    mapping = MANIFEST.get("derived_value_dependencies", {})
    if not isinstance(mapping, dict):
        return {}
    return {
        key: [str(item) for item in value]
        for key, value in mapping.items()
        if isinstance(key, str) and isinstance(value, list)
    }
