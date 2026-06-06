"""Car multi-option comparison.

Ranking several options against each other is structurally different from
checking a single decision, so it is not expressible in the declarative engine.
It lives here as a vetted module; ``domain.py`` dispatches to it when the IR
carries per-option models.
"""

from __future__ import annotations

from typing import Any

from decision_proof.core.next_questions import package_questions, question_item

from . import options as options_mod


def is_option_comparison(ir: dict[str, Any]) -> bool:
    options = ir.get("options", [])
    return any(isinstance(option, dict) and "model" in option for option in options)


def _best_option(run: dict[str, Any]) -> dict[str, Any] | None:
    best_option_id = run.get("recommendation", {}).get("best_option")
    return next(
        (
            item
            for item in run.get("comparison", {}).get("options", [])
            if item.get("id") == best_option_id
        ),
        None,
    )


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    result = options_mod.evaluate_options(ir)
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


def thresholds() -> dict[str, Any]:
    return {
        "current": {
            "unsupported": "option comparison sensitivity is still script-only"
        },
        "flip_conditions": {},
    }


def guidance(run: dict[str, Any]) -> dict[str, str]:
    recommendation = run.get("recommendation", {})
    best_option = _best_option(run)
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


def next_questions(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    del ir
    best_option_id = run.get("recommendation", {}).get("best_option")
    best_option = _best_option(run)
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


def derived_value_dependencies(run: dict[str, Any]) -> dict[str, list[str]]:
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
