"""Resolve and execute Decision Proof domain handlers."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from .domain_metadata import DomainSpec, domain_manifest, domain_specs
from .guidance import default_guidance, manifest_guidance
from .next_questions import default_next_questions, manifest_next_questions


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
    module = import_module(spec.module_name)
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


_NUMERIC_CONSTRAINT_TYPES = {
    "rate_decimal",
    "currency",
    "fraction",
    "years",
    "months",
    "count",
    "number",
}
_CONSTRAINT_HINTS = {
    "rate_decimal": " (rates are decimals, e.g. 0.065 not 6.5)",
    "fraction": " (fractions are 0-1, e.g. 0.20 not 20)",
}


def variable_constraint_errors(ir: dict[str, Any]) -> list[str]:
    """Model-level validation: check provided values against the domain's
    declared ranges/units. Catches errors a schema cannot (a 6.5 rate, a $0
    income, a percentage entered as 20 instead of 0.20)."""
    if not decision_markers(ir):
        return []
    try:
        spec = resolve_domain_spec(ir)
    except DomainRuntimeError:
        return []

    constraints = domain_manifest(spec.model_path).get("variable_constraints", {})
    if not isinstance(constraints, dict):
        return []
    variables = ir.get("variables", {})
    errors: list[str] = []

    for name, rule in constraints.items():
        if not isinstance(rule, dict):
            continue
        variable = variables.get(name)
        if not isinstance(variable, dict):
            continue  # absent is the required-variable check's job
        value = variable.get("value")
        if value is None:  # explicit unknown opens a goal, not a constraint error
            continue

        kind = rule.get("type")
        if kind in _NUMERIC_CONSTRAINT_TYPES:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(
                    f"variables.{name} must be a number ({kind}); got {value!r}"
                )
                continue
            number = float(value)
            hint = _CONSTRAINT_HINTS.get(kind, "")
            if "min" in rule and number < rule["min"]:
                errors.append(
                    f"variables.{name} = {number:g} is below min {rule['min']:g}{hint}"
                )
            if "max" in rule and number > rule["max"]:
                errors.append(
                    f"variables.{name} = {number:g} is above max {rule['max']:g}{hint}"
                )
            if "exclusive_min" in rule and number <= rule["exclusive_min"]:
                errors.append(
                    f"variables.{name} = {number:g} must be greater than {rule['exclusive_min']:g}"
                )
            if "exclusive_max" in rule and number >= rule["exclusive_max"]:
                errors.append(
                    f"variables.{name} = {number:g} must be less than {rule['exclusive_max']:g}"
                )
    return errors


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
    spec, module = load_domain(ir)
    if hasattr(module, "guidance"):
        return module.guidance(run)
    manifest = domain_manifest(spec.model_path)
    if isinstance(manifest.get("guidance_config"), dict):
        return manifest_guidance(run, manifest)
    return default_guidance(run)


def next_questions(
    ir: dict[str, Any], run: dict[str, Any] | None = None
) -> dict[str, Any]:
    spec, module = load_domain(ir)
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
    manifest = domain_manifest(spec.model_path)
    if isinstance(manifest.get("next_questions_config"), dict):
        return manifest_next_questions(ir, active_run, manifest)
    return default_next_questions(ir, active_run)


def _manifest_string_lists(mapping: Any) -> dict[str, list[str]]:
    if not isinstance(mapping, dict):
        return {}
    return {
        key: [str(item) for item in value]
        for key, value in mapping.items()
        if isinstance(key, str) and isinstance(value, list)
    }


def derived_value_dependencies(
    ir: dict[str, Any], run: dict[str, Any]
) -> dict[str, list[str]]:
    spec, module = load_domain(ir)
    if hasattr(module, "derived_value_dependencies"):
        return module.derived_value_dependencies(run)
    manifest = domain_manifest(spec.model_path)
    return _manifest_string_lists(manifest.get("derived_value_dependencies", {}))


def derived_value_assumptions(ir: dict[str, Any]) -> dict[str, list[str]]:
    """Defaulted priors each numeric output depends on, declared in the manifest.

    Unlike dependencies (required, enforced present), these are disclosed-only:
    a prior is satisfied by being explicit in the IR or surfaced in
    ``assumptions_used``.
    """
    spec = resolve_domain_spec(ir)
    manifest = domain_manifest(spec.model_path)
    return _manifest_string_lists(manifest.get("derived_value_assumptions", {}))
