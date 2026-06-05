"""Shared helpers for deterministic next-question selection."""

from __future__ import annotations

from typing import Any


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
        is_weak = source in WEAK_SOURCES or not isinstance(confidence, (int, float)) or confidence < 0.75
        if not is_weak:
            continue
        ranked.append((0 if source in WEAK_SOURCES else 1, confidence if isinstance(confidence, (int, float)) else -1.0, name))
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
            {
                key: value
                for key, value in item.items()
                if key != "priority"
            }
            for item in deduped
        ],
        "why_these_questions": "These questions target the open proof goals, the closest flip conditions, and the weakest evidence among decision-defining variables.",
        "expected_variable_updates": list(dict.fromkeys(variable for item in deduped for variable in item["expected_variable_updates"])),
        "possible_conclusion_impact": [item["possible_conclusion_impact"] for item in deduped],
    }


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