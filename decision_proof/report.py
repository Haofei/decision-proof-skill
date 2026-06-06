"""Report generation helpers for Decision Proof."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from decision_proof.core.domain_runtime import (
    DomainRuntimeError,
    derived_value_assumptions,
    derived_value_dependencies,
    domain_key,
    evaluate,
    guidance,
    thresholds,
    verify,
)
from decision_proof.core.domain_shared import error_payload
from decision_proof.core.global_verifier import verify_run
from decision_proof.core.io import load_json


def canonical_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def variable_rows(
    ir: dict[str, Any], proof_state: dict[str, Any]
) -> list[dict[str, Any]]:
    used_in: dict[str, list[str]] = {}
    for goal in proof_state.get("goals", []):
        for dependency in goal.get("dependencies", []):
            used_in.setdefault(dependency, []).append(goal.get("claim", "unknown_goal"))

    rows = []
    for name, variable in sorted(ir.get("variables", {}).items()):
        if not isinstance(variable, dict):
            continue
        value = variable.get("value")
        rows.append(
            {
                "name": name,
                "value": "unknown" if value is None else value,
                "unit": variable.get("unit"),
                "source": variable.get("source"),
                "confidence": variable.get("confidence"),
                "status": variable.get("status")
                or ("unknown" if value is None else "known"),
                "used_in": sorted(set(used_in.get(name, []))),
            }
        )
    return rows


def make_run(
    ir: dict[str, Any], ir_path: Path, run_id: str | None = None
) -> dict[str, Any]:
    evaluation = evaluate(ir)
    sensitivity = thresholds(ir)
    verifier = verify(ir, ir_path)
    created_at = (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    decision_id = ir.get("decision", {}).get("id", "decision")
    input_hash = canonical_hash(ir)

    run = {
        "run_id": run_id or f"run_{created_at}",
        "decision_id": decision_id,
        "domain": domain_key(ir),
        "created_at": created_at,
        "input_ir_hash": input_hash,
        "input_ir": ir,
        "derived_values": evaluation["derived_values"],
        "proof_state": evaluation["proof_state"],
        "recommendation": evaluation["recommendation"],
        "sensitivity": sensitivity,
        "verifier_result": verifier,
    }
    if "comparison" in evaluation:
        run["comparison"] = evaluation["comparison"]
    if "assumptions_used" in evaluation:
        run["assumptions_used"] = evaluation["assumptions_used"]
    run["derived_value_dependencies"] = derived_value_dependencies(ir, run)
    run["derived_value_assumptions"] = derived_value_assumptions(ir)
    run["guidance"] = guidance(ir, run)
    run["global_verifier_result"] = verify_run(run, expected_hash=input_hash)
    return run


def format_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def goal_mark(status: str) -> str:
    return {
        "closed": "PASS",
        "failed": "FAIL",
        "open": "OPEN",
        "assumption": "ASSUME",
    }.get(status, status.upper())


def verifier_badge(verifier: dict[str, Any]) -> str:
    if not verifier.get("proof_checked"):
        return (
            f"OPEN: Not proof-checked ({verifier.get('error', 'verifier incomplete')})"
        )
    return (
        f"PASS: Deterministic domain checks passed ({verifier.get('proved_predicate')})"
    )


def render_markdown(run: dict[str, Any]) -> str:
    ir = run["input_ir"]
    decision = ir.get("decision", {})
    recommendation = run["recommendation"]
    derived = run["derived_values"]
    proof_state = run["proof_state"]
    sensitivity = run["sensitivity"]
    variables = variable_rows(ir, proof_state)
    comparison = run.get("comparison", {})
    guidance = run.get("guidance", {})

    lines = [
        f"# Decision Report: {decision.get('question', decision.get('id', 'Untitled decision'))}",
        "",
        "## Current Conclusion",
        "",
        f"- Status: `{recommendation.get('status')}`",
        f"- Evidence quality: `{recommendation.get('evidence_quality')}`",
        f"- Verification: {verifier_badge(run.get('verifier_result', {}))}",
    ]

    if guidance.get("summary"):
        lines.append(f"- Actionable conclusion: {guidance['summary']}")

    lines.extend(
        [
            "",
            "## Decision Guidance",
            "",
            f"- Focus on: {guidance.get('focus')}",
            f"- Do not overthink: {guidance.get('deprioritize')}",
            f"- Next step: {guidance.get('next_step')}",
        ]
    )
    if guidance.get("tradeoff"):
        lines.append(f"- Price the soft factor honestly: {guidance['tradeoff']}")

    lines.extend(["", "## Key Derived Values", ""])
    for key, value in derived.items():
        lines.append(f"- `{key}`: {format_value(value)}")

    assumptions = run.get("assumptions_used", {})
    if assumptions:
        lines.extend(
            [
                "",
                "## Default Assumptions (priors)",
                "",
                "_Applied because the input did not specify them. They shaped the result and are not user-verified facts._",
                "",
            ]
        )
        for key, value in assumptions.items():
            rendered = (
                format(value, "g") if isinstance(value, (int, float)) else str(value)
            )
            lines.append(f"- `{key}`: {rendered}")

    if comparison.get("options"):
        lines.extend(["", "## Option Ranking", ""])
        ranking = comparison.get("ranking", [])
        options_by_id = {
            option.get("id"): option for option in comparison.get("options", [])
        }
        for option_id in ranking:
            option = options_by_id.get(option_id, {})
            net_value = option.get("derived_values", {}).get("net_monthly_value")
            lines.append(
                f"- `{option.get('label', option_id)}` ({option_id}): `{option.get('status')}`, net_monthly_value={format_value(net_value)}"
            )

    lines.extend(["", "## Flip Conditions", ""])
    for key, value in sensitivity.get("flip_conditions", {}).items():
        lines.append(f"- `{key}`: {format_value(value)}")

    unknowns = sensitivity.get("current", {}).get("unknown_variables", [])
    if unknowns:
        lines.extend(["", "## Unknown Variables Affecting Sensitivity", ""])
        for name in unknowns:
            lines.append(f"- `{name}`")

    lines.extend(["", "## Proof Goals", ""])
    for proof_goal in proof_state.get("goals", []):
        lines.append(
            f"- {goal_mark(proof_goal.get('status', 'unknown'))}: `{proof_goal.get('claim')}` - {proof_goal.get('reason')}"
        )

    lines.extend(
        [
            "",
            "## Variables / Evidence Table",
            "",
            "| Variable | Value | Unit | Source | Confidence | Status | Used In |",
            "| --- | ---: | --- | --- | ---: | --- | --- |",
        ]
    )
    for row in variables:
        used_in = ", ".join(row["used_in"]) if row["used_in"] else ""
        lines.append(
            f"| `{row['name']}` | {format_value(row['value'])} | {format_value(row['unit'])} | "
            f"{format_value(row['source'])} | {format_value(row['confidence'])} | {format_value(row['status'])} | {used_in} |"
        )

    open_goals = [
        goal
        for goal in proof_state.get("goals", [])
        if goal.get("status") in {"open", "assumption"}
    ]
    if open_goals:
        lines.extend(["", "## Next Evidence", ""])
        seen = set()
        for proof_goal in open_goals:
            for dependency in proof_goal.get("dependencies", []):
                if dependency in seen:
                    continue
                seen.add(dependency)
                lines.append(
                    f"- Clarify `{dependency}` for `{proof_goal.get('claim')}`."
                )

    lines.extend(
        ["", f"_Run: `{run['run_id']}`. Input hash: `{run['input_ir_hash']}`._", ""]
    )
    return "\n".join(lines)


__all__ = [
    "DomainRuntimeError",
    "canonical_hash",
    "error_payload",
    "format_value",
    "goal_mark",
    "load_json",
    "make_run",
    "render_markdown",
    "variable_rows",
    "verifier_badge",
]
