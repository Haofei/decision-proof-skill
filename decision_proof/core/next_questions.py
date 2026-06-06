"""Shared helpers for deterministic next-question selection."""

from __future__ import annotations

from typing import Any

from .guidance import (
    goal_lookup,
    manifest_lever_candidates,
    rank_flip_levers,
    render_manifest_template,
)

WEAK_SOURCES = {"guessed", "unknown"}


def question_item(
    *,
    question_id: str,
    question: str,
    why_this_question: str,
    expected_variable_updates: list[str],
    possible_conclusion_impact: str,
    priority: int,
) -> dict[str, Any]:
    return {
        "id": question_id,
        "question": question,
        "why_this_question": why_this_question,
        "expected_variable_updates": expected_variable_updates,
        "possible_conclusion_impact": possible_conclusion_impact,
        "priority": priority,
    }


def variable_record(ir: dict[str, Any], name: str) -> dict[str, Any]:
    variable = ir.get("variables", {}).get(name, {})
    return variable if isinstance(variable, dict) else {}


def low_evidence_variables(ir: dict[str, Any], names: list[str]) -> list[str]:
    ranked = []
    for name in names:
        record = variable_record(ir, name)
        if not record:
            continue
        confidence = record.get("confidence")
        source = record.get("source")
        is_weak = (
            source in WEAK_SOURCES
            or not isinstance(confidence, (int, float))
            or confidence < 0.75
        )
        if not is_weak:
            continue
        ranked.append(
            (
                0 if source in WEAK_SOURCES else 1,
                confidence if isinstance(confidence, (int, float)) else -1.0,
                name,
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [name for _, _, name in ranked]


def package_questions(items: list[dict[str, Any]]) -> dict[str, Any]:
    deduped = []
    seen_ids = set()
    seen_questions = set()
    for item in sorted(items, key=lambda entry: entry.get("priority", 0), reverse=True):
        if item["id"] in seen_ids or item["question"] in seen_questions:
            continue
        seen_ids.add(item["id"])
        seen_questions.add(item["question"])
        deduped.append(item)
        if len(deduped) == 5:
            break

    return {
        "next_questions": [
            {key: value for key, value in item.items() if key != "priority"}
            for item in deduped
        ],
        "why_these_questions": "These questions target the open proof goals, the closest flip conditions, and the weakest evidence among decision-defining variables.",
        "expected_variable_updates": list(
            dict.fromkeys(
                variable
                for item in deduped
                for variable in item["expected_variable_updates"]
            )
        ),
        "possible_conclusion_impact": [
            item["possible_conclusion_impact"] for item in deduped
        ],
    }


def _condition_matches(
    condition: dict[str, Any] | None,
    *,
    ir: dict[str, Any],
    goal_map: dict[str, dict[str, Any]],
    top_lever: str | None,
) -> bool:
    if not condition:
        return True
    if "any" in condition:
        return any(
            _condition_matches(item, ir=ir, goal_map=goal_map, top_lever=top_lever)
            for item in condition["any"]
            if isinstance(item, dict)
        )
    if "all" in condition:
        return all(
            _condition_matches(item, ir=ir, goal_map=goal_map, top_lever=top_lever)
            for item in condition["all"]
            if isinstance(item, dict)
        )
    if "variable_unknown" in condition:
        return (
            variable_record(ir, str(condition["variable_unknown"])).get("value") is None
        )
    if "goal_status" in condition:
        goal_status = condition["goal_status"]
        claim = str(goal_status.get("claim") or "")
        statuses = goal_status.get("statuses", [])
        if isinstance(statuses, str):
            statuses = [statuses]
        return goal_map.get(claim, {}).get("status") in {str(item) for item in statuses}
    if "top_lever" in condition:
        return top_lever == str(condition["top_lever"])
    if "low_evidence_any" in condition:
        names = [str(item) for item in condition["low_evidence_any"]]
        return bool(low_evidence_variables(ir, names))
    if "low_evidence_variable" in condition:
        name = str(condition["low_evidence_variable"])
        return name in low_evidence_variables(ir, [name])
    return False


def manifest_next_questions(
    ir: dict[str, Any], run: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    config = (
        manifest.get("next_questions_config", {}) if isinstance(manifest, dict) else {}
    )
    if not isinstance(config, dict) or config.get("mode") != "rules":
        return default_next_questions(ir, run)

    goal_map = goal_lookup(run.get("proof_state", {}))
    guidance_config = (
        manifest.get("guidance_config", {}) if isinstance(manifest, dict) else {}
    )
    positive_statuses = {
        str(item)
        for item in guidance_config.get("positive_statuses", ["lean_yes", "recommend"])
    }
    positive_case = run.get("recommendation", {}).get("status") in positive_statuses
    top_lever = None
    levers = (
        guidance_config.get("levers", []) if isinstance(guidance_config, dict) else []
    )
    if isinstance(levers, list) and levers:
        ranked = rank_flip_levers(
            manifest_lever_candidates(run, levers), positive_case=positive_case
        )
        top_lever = ranked[0]["label"] if ranked else None

    items = []
    for rule in config.get("rules", []):
        if not isinstance(rule, dict):
            continue
        if not _condition_matches(
            rule.get("when"), ir=ir, goal_map=goal_map, top_lever=top_lever
        ):
            continue
        priority = int(rule.get("priority", 0))
        if top_lever == rule.get("top_lever") and "priority_if_top_lever" in rule:
            priority = int(rule.get("priority_if_top_lever", priority))
        why_this_question = render_manifest_template(
            rule.get("why_template"), rule.get("why_placeholders", {}), run, goal_map
        )
        items.append(
            question_item(
                question_id=str(rule.get("question_id") or "unknown.question"),
                question=str(rule.get("question") or ""),
                why_this_question=str(
                    why_this_question or rule.get("why_this_question") or ""
                ),
                expected_variable_updates=[
                    str(item) for item in rule.get("expected_variable_updates", [])
                ],
                possible_conclusion_impact=str(
                    rule.get("possible_conclusion_impact") or ""
                ),
                priority=priority,
            )
        )
    return package_questions(items)


def default_next_questions(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    del ir, run
    return package_questions(
        [
            question_item(
                question_id="default.closest_flip",
                question="Which single input do you trust least among the variables driving this decision?",
                why_this_question="The runtime can evaluate the current model, but it still needs one stronger fact on the nearest flip condition.",
                expected_variable_updates=[],
                possible_conclusion_impact="Could move the conclusion from conditional to stable.",
                priority=10,
            )
        ]
    )


__all__ = [
    "default_next_questions",
    "low_evidence_variables",
    "manifest_next_questions",
    "package_questions",
    "question_item",
    "variable_record",
]
