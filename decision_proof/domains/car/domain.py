"""Car domain adapter.

The single-decision path (cash safety, affordability, time-value benefit) is the
hand-written evaluator/sensitivity in this package; the multi-option ranking path
lives in ``comparison``. This module only dispatches between them and runs the
deterministic single-decision verifier. Manifest config drives single-decision
guidance and next-questions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_proof.core.domain_metadata import domain_manifest
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

from . import comparison as comparison_mod
from . import evaluator as evaluate_mod
from . import sensitivity as sensitivity_mod

MANIFEST = domain_manifest(Path(__file__).with_name("manifest.json"))


def _is_comparison_run(run: dict[str, Any]) -> bool:
    return bool(run.get("comparison", {}).get("options"))


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    if comparison_mod.is_option_comparison(ir):
        return comparison_mod.evaluate(ir)
    return evaluate_mod.evaluate(ir)


def thresholds(ir: dict[str, Any]) -> dict[str, Any]:
    if comparison_mod.is_option_comparison(ir):
        return comparison_mod.thresholds()
    return sensitivity_mod.thresholds(ir)


def verify(ir_path: Path) -> dict[str, Any]:
    """Deterministic domain invariants for a single-decision car IR."""
    ir = load_ir(ir_path)
    if comparison_mod.is_option_comparison(ir):
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


def guidance(run: dict[str, Any]) -> dict[str, str]:
    if _is_comparison_run(run):
        return comparison_mod.guidance(run)
    return manifest_guidance(run, MANIFEST)


def next_questions(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    if _is_comparison_run(run):
        return comparison_mod.next_questions(ir, run)
    return manifest_next_questions(ir, run, MANIFEST)


def derived_value_dependencies(run: dict[str, Any]) -> dict[str, list[str]]:
    if _is_comparison_run(run):
        return comparison_mod.derived_value_dependencies(run)
    mapping = MANIFEST.get("derived_value_dependencies", {})
    if not isinstance(mapping, dict):
        return {}
    return {
        key: [str(item) for item in value]
        for key, value in mapping.items()
        if isinstance(key, str) and isinstance(value, list)
    }
