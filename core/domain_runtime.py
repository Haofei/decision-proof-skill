#!/usr/bin/env python3
"""Resolve and execute Decision Proof domain handlers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.domain_metadata import DomainSpec, domain_specs  # noqa: E402
from core.guidance import default_guidance  # noqa: E402
from core.next_questions import default_next_questions  # noqa: E402
from core.domain_shared import load_module  # noqa: E402


class DomainRuntimeError(ValueError):
    """Raised when an IR cannot be mapped to a supported domain."""


def decision_markers(ir: dict[str, Any]) -> list[str]:
    decision = ir.get("decision", {})
    markers: list[str] = []
    if not isinstance(decision, dict):
        return markers
    for key in ("domain", "type"):
        value = decision.get(key)
        if isinstance(value, str) and value:
            markers.append(value)
    return markers


def available_domain_specs() -> tuple[DomainSpec, ...]:
    return domain_specs()


def resolve_domain_spec(ir: dict[str, Any]) -> DomainSpec:
    markers = decision_markers(ir)
    for marker in markers:
        normalized = marker.strip().lower().replace(" ", "_")
        for spec in available_domain_specs():
            if normalized == spec.key or normalized in spec.decision_types:
                return spec
    detail = ", ".join(markers) if markers else "missing decision.domain/type"
    raise DomainRuntimeError(f"unsupported decision domain/type: {detail}")


def load_domain(ir: dict[str, Any]) -> tuple[DomainSpec, Any]:
    spec = resolve_domain_spec(ir)
    module = load_module(f"decision_proof_domain_{spec.key}", spec.module_path)
    return spec, module


def domain_key(ir: dict[str, Any]) -> str:
    return resolve_domain_spec(ir).key


def validation_errors(ir: dict[str, Any]) -> list[str]:
    if not decision_markers(ir):
        return []

    try:
        spec = resolve_domain_spec(ir)
    except DomainRuntimeError as exc:
        return [str(exc)]

    variables = ir.get("variables", {})
    if not isinstance(variables, dict):
        return []

    missing = [name for name in spec.required_variables if name not in variables]
    if not missing:
        return []
    return [f"missing required variables for domain '{spec.key}': {', '.join(missing)}"]


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    _, module = load_domain(ir)
    return module.evaluate(ir)


def thresholds(ir: dict[str, Any]) -> dict[str, Any]:
    _, module = load_domain(ir)
    if hasattr(module, "thresholds"):
        return module.thresholds(ir)
    return {"current": {}, "flip_conditions": {}}


def verify(ir: dict[str, Any], ir_path: Path) -> dict[str, Any]:
    _, module = load_domain(ir)
    if hasattr(module, "verify"):
        return module.verify(ir_path)
    return {
        "ok": False,
        "proof_checked": False,
        "error": f"verifier not implemented for domain '{domain_key(ir)}'",
    }


def guidance(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, str]:
    _, module = load_domain(ir)
    if hasattr(module, "guidance"):
        return module.guidance(run)
    return default_guidance(run)


def next_questions(ir: dict[str, Any], run: dict[str, Any] | None = None) -> dict[str, Any]:
    _, module = load_domain(ir)
    active_run = run
    if active_run is None:
        evaluation = evaluate(ir)
        active_run = {
            "domain": domain_key(ir),
            "input_ir": ir,
            "derived_values": evaluation["derived_values"],
            "proof_state": evaluation["proof_state"],
            "recommendation": evaluation["recommendation"],
            "sensitivity": thresholds(ir),
        }
        if "comparison" in evaluation:
            active_run["comparison"] = evaluation["comparison"]
    if hasattr(module, "next_questions"):
        return module.next_questions(ir, active_run)
    return default_next_questions(ir, active_run)


def derived_value_dependencies(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, list[str]]:
    _, module = load_domain(ir)
    if hasattr(module, "derived_value_dependencies"):
        return module.derived_value_dependencies(run)
    return {}