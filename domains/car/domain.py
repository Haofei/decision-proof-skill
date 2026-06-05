"""Car domain adapters for the Decision Proof core runtime."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.guidance import describe_top_flip_lever, first_goal_with_status, format_currency, goal_lookup  # noqa: E402
from core.guidance import rank_flip_levers  # noqa: E402
from core.next_questions import low_evidence_variables, package_questions, question_item, variable_record  # noqa: E402
from domains.car import evaluator as evaluate_mod  # noqa: E402
from domains.car import options as options_mod  # noqa: E402
from domains.car import sensitivity as sensitivity_mod  # noqa: E402
from domains.car import verifier as verifier_mod  # noqa: E402


def is_option_comparison(ir: dict[str, Any]) -> bool:
    options = ir.get("options", [])
    return any(isinstance(option, dict) and "model" in option for option in options)


def normalize_option_comparison(result: dict[str, Any]) -> dict[str, Any]:
    best_option_id = result.get("recommendation", {}).get("best_option")
    best_option = next((option for option in result.get("options", []) if option.get("id") == best_option_id), None)
    proof_state = best_option.get("proof_state") if best_option else {"target_claim": result.get("target_claim"), "goals": []}
    return {
        "derived_values": {
            "best_option": best_option_id,
            "best_option_net_monthly_value": best_option.get("derived_values", {}).get("net_monthly_value") if best_option else None,
            "best_option_cost_income_ratio": best_option.get("derived_values", {}).get("cost_income_ratio") if best_option else None,
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
            "current": {"unsupported": "option comparison sensitivity is still script-only"},
            "flip_conditions": {},
        }
    return sensitivity_mod.thresholds(ir)


def verify(ir_path: Path) -> dict[str, Any]:
    ir = verifier_mod.load_json(ir_path)
    if is_option_comparison(ir):
        return {
            "ok": False,
            "proof_checked": False,
            "error": "verifier not implemented for car option comparison",
        }

    try:
        return verifier_mod.verify_ir(ir_path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "proof_checked": False, "error": str(exc)}


def car_constraint_deprioritize(proof_state: dict[str, Any]) -> str | None:
    goal_map = goal_lookup(proof_state)
    passed = []
    if goal_map.get("cash_safety", {}).get("status") == "closed":
        passed.append("emergency-fund safety")
    if goal_map.get("income_affordability", {}).get("status") == "closed":
        passed.append("income affordability")
    if not passed:
        return None
    if len(passed) == 1:
        return f"{passed[0].capitalize()} already passes; do not keep re-estimating it unless the number materially changes."
    return f"{passed[0].capitalize()} and {passed[1]} already pass; do not keep re-estimating them unless the numbers materially change."


def car_focus_signal(run: dict[str, Any]) -> tuple[str | None, str | None]:
    status = run.get("recommendation", {}).get("status")
    current = run.get("sensitivity", {}).get("current", {})
    flip = run.get("sensitivity", {}).get("flip_conditions", {})
    positive_case = status in {"lean_yes", "recommend"}

    if current.get("value_of_time") is None and isinstance(flip.get("break_even_value_of_time"), (int, float)):
        threshold = format_currency(flip["break_even_value_of_time"], "/hour")
        return (
            f"The decision currently turns on one unknown: whether your time is worth at least {threshold}.",
            "Decide what one regained hour is actually worth to you before tuning anything else.",
        )

    candidates = [
        {
            "label": "your time value",
            "current_value": current.get("value_of_time"),
            "threshold_value": flip.get("break_even_value_of_time"),
            "higher_is_better": True,
            "current_text": format_currency(current.get("value_of_time"), "/hour"),
            "threshold_text": format_currency(flip.get("break_even_value_of_time"), "/hour"),
            "next_step": "Decide what one regained hour is actually worth to you.",
        },
        {
            "label": "all-in monthly car cost",
            "current_value": current.get("monthly_car_cost"),
            "threshold_value": flip.get("break_even_monthly_car_cost"),
            "higher_is_better": False,
            "current_text": format_currency(current.get("monthly_car_cost"), "/month"),
            "threshold_text": format_currency(flip.get("break_even_monthly_car_cost"), "/month"),
            "next_step": "Get a real all-in monthly car quote before changing anything else.",
        },
        {
            "label": "monthly time saved",
            "current_value": current.get("known_monthly_time_saved_hours"),
            "threshold_value": flip.get("break_even_time_saved_hours"),
            "higher_is_better": True,
            "current_text": f"{current.get('known_monthly_time_saved_hours')} hours/month" if current.get("known_monthly_time_saved_hours") is not None else "unknown",
            "threshold_text": f"{flip.get('break_even_time_saved_hours')} hours/month" if flip.get("break_even_time_saved_hours") is not None else "unknown",
            "next_step": "Measure actual commute and errand time savings before changing anything else.",
        },
    ]
    return describe_top_flip_lever(candidates, positive_case=positive_case)


def build_comparison_guidance(run: dict[str, Any]) -> dict[str, str]:
    comparison = run.get("comparison", {})
    recommendation = run.get("recommendation", {})
    best_option_id = recommendation.get("best_option")
    best_option = next((item for item in comparison.get("options", []) if item.get("id") == best_option_id), None)
    main_risk = best_option.get("main_risk") if isinstance(best_option, dict) else None
    return {
        "summary": recommendation.get("summary", "Use the ranking as a shortlist, not as a reason to micromanage every option."),
        "focus": main_risk or "Validate the main risk on the top-ranked option before over-optimizing the rest of the list.",
        "deprioritize": "Do not overfit tiny ranking differences across every option before checking the top option's main risk.",
        "next_step": "Get one stronger fact on the top-ranked option before revisiting the ranking.",
    }


def build_single_decision_guidance(run: dict[str, Any]) -> dict[str, str]:
    proof_state = run.get("proof_state", {})
    status = run.get("recommendation", {}).get("status")
    flip = run.get("sensitivity", {}).get("flip_conditions", {})
    hard_fail = first_goal_with_status(proof_state, {"cash_safety", "income_affordability"}, "failed", severity="hard")
    deprioritize = car_constraint_deprioritize(proof_state)

    if hard_fail is not None:
        next_step = "Revisit the decision only after the hard constraint is back inside the safe range."
        if hard_fail.get("claim") == "income_affordability" and isinstance(flip.get("break_even_monthly_car_cost"), (int, float)):
            next_step = f"Get the all-in monthly cost below about {format_currency(flip['break_even_monthly_car_cost'], '/month')} or change the income assumptions."
        return {
            "summary": "Do not treat this as a soft-preference choice yet; a hard constraint is failing.",
            "focus": hard_fail.get("reason", "A hard constraint is failing."),
            "deprioritize": deprioritize or "Do not spend more time on softer upside until the hard constraint is resolved.",
            "next_step": next_step,
        }

    focus, next_step = car_focus_signal(run)
    premium = flip.get("required_lifestyle_premium")

    if status == "insufficient_evidence" and focus:
        summary = "Do not force a conclusion yet. The model is mostly waiting on one decision-defining number, not on every unknown."
    elif status in {"lean_no", "do_not_recommend"} and isinstance(premium, (int, float)) and premium > 0:
        summary = f"Tilt against buying on the current numbers. If nothing else changes, this is effectively a {format_currency(premium, '/month')} comfort and flexibility purchase."
    elif status in {"lean_yes", "recommend"}:
        summary = "Tilt toward buying, but the case is not evenly sensitive across all inputs."
    else:
        summary = "The current conclusion is conditional; the next step is to resolve the closest flip line, not to argue every variable at once."

    guidance = {
        "summary": summary,
        "focus": focus or "The model has enough math, but it still needs one concrete lever clarified before the conclusion is trustworthy.",
        "deprioritize": deprioritize or "Do not spread effort evenly across every estimate; follow the closest flip line first.",
        "next_step": next_step or "Clarify the single variable that sits closest to the flip line.",
    }
    if isinstance(premium, (int, float)) and premium > 0:
        guidance["tradeoff"] = f"If the factual inputs stay where they are, ask explicitly whether you would knowingly pay {format_currency(premium, '/month')} for comfort and optionality."
    return guidance


def guidance(run: dict[str, Any]) -> dict[str, str]:
    if run.get("comparison", {}).get("options"):
        return build_comparison_guidance(run)
    return build_single_decision_guidance(run)


def next_questions(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    if run.get("comparison", {}).get("options"):
        comparison = run.get("comparison", {})
        recommendation = run.get("recommendation", {})
        best_option_id = recommendation.get("best_option")
        best_option = next((item for item in comparison.get("options", []) if item.get("id") == best_option_id), None)
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
                if goal_item.get("claim") == "income_affordability" and goal_item.get("status") == "open":
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
                if goal_item.get("claim") == "utility_result" and goal_item.get("status") == "open":
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

    proof_state = run.get("proof_state", {})
    goal_map = goal_lookup(proof_state)
    current = run.get("sensitivity", {}).get("current", {})
    flip = run.get("sensitivity", {}).get("flip_conditions", {})
    status = run.get("recommendation", {}).get("status")
    positive_case = status in {"lean_yes", "recommend"}

    candidates = [
        {
            "label": "your time value",
            "current_value": current.get("value_of_time"),
            "threshold_value": flip.get("break_even_value_of_time"),
            "higher_is_better": True,
        },
        {
            "label": "all-in monthly car cost",
            "current_value": current.get("monthly_car_cost"),
            "threshold_value": flip.get("break_even_monthly_car_cost"),
            "higher_is_better": False,
        },
        {
            "label": "monthly time saved",
            "current_value": current.get("known_monthly_time_saved_hours"),
            "threshold_value": flip.get("break_even_time_saved_hours"),
            "higher_is_better": True,
        },
    ]
    ranked = rank_flip_levers(candidates, positive_case=positive_case)
    top_label = ranked[0]["label"] if ranked else None

    items = []
    value_of_time = variable_record(ir, "value_of_time")
    if value_of_time.get("value") is None:
        threshold = format_currency(flip.get("break_even_value_of_time"), "/hour")
        items.append(
            question_item(
                question_id="car.value_of_time",
                question="What is one regained hour actually worth to you for this decision? A range is enough.",
                why_this_question=f"`benefit_exceeds_incremental_cost` is still open, and the closest flip line currently sits around {threshold}.",
                expected_variable_updates=["value_of_time"],
                possible_conclusion_impact="Could move the conclusion from insufficient_evidence to lean_yes or lean_no.",
                priority=100,
            )
        )
    elif top_label == "your time value" or "value_of_time" in low_evidence_variables(ir, ["value_of_time"]):
        threshold = format_currency(flip.get("break_even_value_of_time"), "/hour")
        items.append(
            question_item(
                question_id="car.value_of_time.evidence",
                question="How would you justify your current value_of_time number with one concrete benchmark?",
                why_this_question=f"The nearest flip condition still runs through `value_of_time`, with a break-even point near {threshold}.",
                expected_variable_updates=["value_of_time"],
                possible_conclusion_impact="Could stabilize the current conclusion or flip it if your true time value is on the other side of the threshold.",
                priority=85,
            )
        )

    if top_label == "all-in monthly car cost" or "monthly_car_cost" in low_evidence_variables(ir, ["monthly_car_cost"]):
        threshold = format_currency(flip.get("break_even_monthly_car_cost"), "/month")
        items.append(
            question_item(
                question_id="car.monthly_car_cost",
                question="What is the real all-in monthly car cost once insurance, parking, maintenance, and financing are included?",
                why_this_question=f"Affordability and net value both move with this input, and the current break-even line is about {threshold}.",
                expected_variable_updates=["monthly_car_cost"],
                possible_conclusion_impact="Could flip the recommendation or turn a warning-level affordability issue into a hard fail.",
                priority=90 if top_label == "all-in monthly car cost" else 70,
            )
        )

    if top_label == "monthly time saved" or any(name in low_evidence_variables(ir, ["commute_days_per_month", "current_minutes_each_way", "car_minutes_each_way"]) for name in ["commute_days_per_month", "current_minutes_each_way", "car_minutes_each_way"]):
        hours = flip.get("break_even_time_saved_hours")
        threshold_text = f"{hours} hours/month" if isinstance(hours, (int, float)) else "the break-even time-saved threshold"
        items.append(
            question_item(
                question_id="car.time_saved",
                question="What does one representative week of actual commute and errand time savings look like?",
                why_this_question=f"The conclusion is close to {threshold_text}, so small timing errors can dominate the result.",
                expected_variable_updates=["commute_days_per_month", "current_minutes_each_way", "car_minutes_each_way", "non_commute_trips_per_month", "average_non_commute_minutes_saved"],
                possible_conclusion_impact="Could materially change monthly_time_saved_hours and move the case across its flip line.",
                priority=80,
            )
        )

    if goal_map.get("future_need_stability", {}).get("status") in {"open", "assumption"}:
        items.append(
            question_item(
                question_id="car.need_stability",
                question="How likely is this transport need to stay in place for at least the next 12 months?",
                why_this_question="The model still treats future need stability as unresolved or assumed, which affects how much to trust the upside.",
                expected_variable_updates=["expected_need_stability_months"],
                possible_conclusion_impact="Could increase or decrease confidence in a borderline recommendation.",
                priority=60,
            )
        )

    if variable_record(ir, "monthly_after_tax_income").get("value") is None:
        items.append(
            question_item(
                question_id="car.monthly_income",
                question="What after-tax monthly income should this decision use right now?",
                why_this_question="Income affordability is still open without a current after-tax income number.",
                expected_variable_updates=["monthly_after_tax_income"],
                possible_conclusion_impact="Could move affordability from open to pass, warning, or hard fail.",
                priority=95,
            )
        )

    return package_questions(items)


def derived_value_dependencies(run: dict[str, Any]) -> dict[str, list[str]]:
    if run.get("comparison", {}).get("options"):
        best_option_id = run.get("recommendation", {}).get("best_option")
        option_ids = [item.get("id") for item in run.get("comparison", {}).get("options", []) if isinstance(item, dict) and item.get("id")]
        option_cost_deps = [f"{option_id}.monthly_cost" for option_id in option_ids]
        mapping = {
            "best_option": option_cost_deps or [best_option_id] if best_option_id else option_cost_deps,
            "best_option_net_monthly_value": [f"{best_option_id}.monthly_cost", f"{best_option_id}.monthly_time_saved_hours", "value_of_time"] if best_option_id else option_cost_deps,
            "best_option_cost_income_ratio": [f"{best_option_id}.monthly_cost", "monthly_after_tax_income"] if best_option_id else option_cost_deps,
            "ranking": option_cost_deps,
        }
        return {key: value for key, value in mapping.items() if value}

    time_saved_dependencies = [
        "commute_days_per_month",
        "current_minutes_each_way",
        "car_minutes_each_way",
        "non_commute_trips_per_month",
        "average_non_commute_minutes_saved",
    ]
    return {
        "monthly_commute_time_saved_hours": ["commute_days_per_month", "current_minutes_each_way", "car_minutes_each_way"],
        "monthly_non_commute_time_saved_hours": ["non_commute_trips_per_month", "average_non_commute_minutes_saved"],
        "monthly_time_saved_hours": time_saved_dependencies,
        "monthly_time_value": time_saved_dependencies + ["value_of_time"],
        "incremental_car_cost": ["monthly_car_cost", "current_transport_monthly_cost"],
        "net_monthly_value": time_saved_dependencies + ["value_of_time", "comfort_value_monthly", "optionality_value_monthly", "monthly_car_cost", "current_transport_monthly_cost"],
        "car_cost_income_ratio": ["monthly_car_cost", "monthly_after_tax_income"],
    }