"""Graduate-school domain.

The methodology — variables, formulas, constraints, recommendation mapping, and
sensitivity — is declared in ``manifest.json`` and executed by the shared
``model_engine``. There is no hand-written model math here: ``evaluate`` and
``thresholds`` are one-line delegations, and the rest is wiring (verifier
invariants, manifest-driven guidance and next-questions).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_proof.core import model_engine
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

MANIFEST = domain_manifest(Path(__file__).with_name("manifest.json"))


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    return model_engine.evaluate(ir, MANIFEST)


def thresholds(ir: dict[str, Any]) -> dict[str, Any]:
    return model_engine.thresholds(ir, MANIFEST)


def verify(ir_path: Path) -> dict[str, Any]:
    """Deterministic domain invariants."""
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
