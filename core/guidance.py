"""Shared guidance helpers for decision reports."""

from __future__ import annotations

from typing import Any


def format_currency(value: Any, suffix: str = "") -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    amount = float(value)
    if abs(amount) >= 1000:
        rendered = f"${amount:,.0f}"
        return f"{rendered}{suffix}"
    rounded_int = round(amount)
    rounded_tenth = round(amount, 1)
    if abs(amount - rounded_int) < 1e-9:
        rendered = f"${amount:,.0f}"
    elif abs(amount - rounded_tenth) < 1e-9:
        rendered = f"${amount:,.1f}"
    else:
        rendered = f"${amount:,.2f}"
    return f"{rendered}{suffix}"


def goal_lookup(proof_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {goal.get("claim"): goal for goal in proof_state.get("goals", []) if goal.get("claim")}


def first_goal_with_status(proof_state: dict[str, Any], claims: set[str], status: str) -> dict[str, Any] | None:
    for item in proof_state.get("goals", []):
        if item.get("claim") in claims and item.get("status") == status:
            return item
    return None


def rank_flip_levers(candidates: list[dict[str, Any]], *, positive_case: bool) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        current_value = candidate.get("current_value")
        threshold_value = candidate.get("threshold_value")
        higher_is_better = bool(candidate.get("higher_is_better"))
        if not isinstance(current_value, (int, float)) or not isinstance(threshold_value, (int, float)):
            continue
        if positive_case:
            delta = (current_value - threshold_value) if higher_is_better else (threshold_value - current_value)
        else:
            delta = (threshold_value - current_value) if higher_is_better else (current_value - threshold_value)
        if delta < 0:
            continue
        scale = max(abs(float(threshold_value)), 1.0)
        ranked.append({**candidate, "distance": delta / scale})
    return sorted(ranked, key=lambda item: item["distance"])


def describe_top_flip_lever(candidates: list[dict[str, Any]], *, positive_case: bool) -> tuple[str | None, str | None]:
    ranked = rank_flip_levers(candidates, positive_case=positive_case)
    if not ranked:
        return (None, None)

    focus = ranked[0]
    if positive_case:
        relation = "above" if focus["higher_is_better"] else "below"
        sentence = (
            f"The conclusion is most sensitive to {focus['label']}. It stays favorable while it remains {relation} "
            f"{focus['threshold_text']}; you are currently at {focus['current_text']}."
        )
    else:
        relation = "up to" if focus["higher_is_better"] else "down to"
        sentence = (
            f"The closest way to flip this is {focus['label']}. It would need to move {relation} "
            f"{focus['threshold_text']}; you are currently at {focus['current_text']}."
        )
    return sentence, focus.get("next_step")


def default_guidance(run: dict[str, Any]) -> dict[str, str]:
    return {
        "summary": "The current conclusion is conditional.",
        "focus": "Follow the closest flip condition before broadening the analysis.",
        "deprioritize": "Do not spread effort evenly across every estimate.",
        "next_step": "Resolve the next conclusion-changing variable.",
    }