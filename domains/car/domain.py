"""Car domain adapters for the Decision Proof core runtime."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.domain_shared import load_module  # noqa: E402
from core.guidance import describe_top_flip_lever, first_goal_with_status, format_currency, goal_lookup  # noqa: E402


evaluate_mod = load_module("car_evaluate", ROOT / "scripts" / "evaluate_car_decision.py")
options_mod = load_module("car_options", ROOT / "scripts" / "evaluate_car_options.py")
sensitivity_mod = load_module("car_sensitivity", ROOT / "scripts" / "sensitivity.py")
verifier_mod = load_module("car_verifier", ROOT / "scripts" / "generate_lean_car_proof.py")


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
        data = verifier_mod.derive(ir)
        lean_source = verifier_mod.render_lean(data)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "proof_checked": False, "error": str(exc)}

    lean = shutil.which("lean")
    if not lean:
        return {"ok": False, "proof_checked": False, "error": "lean executable not found"}

    with tempfile.TemporaryDirectory(prefix="decision-proof-car-lean-") as tempdir:
        lean_path = Path(tempdir) / "CarDecisionProof.lean"
        lean_path.write_text(lean_source, encoding="utf-8")
        proc = subprocess.run([lean, str(lean_path)], text=True, capture_output=True, check=False)
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
    hard_fail = first_goal_with_status(proof_state, {"cash_safety", "income_affordability"}, "failed")
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