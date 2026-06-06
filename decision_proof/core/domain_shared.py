"""Shared helpers for domain evaluators and runtime entrypoints."""

from __future__ import annotations

import importlib.util
import operator
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

WEAK_SOURCES = {"guessed", "unknown"}
DEFAULT_GOAL_SEVERITY = {
    "closed": "soft",
    "open": "warning",
    "assumption": "warning",
    "failed": "hard",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def goal(
    goal_id: str,
    claim: str,
    status: str,
    reason: str,
    dependencies: list[str],
    *,
    severity: str | None = None,
) -> dict[str, Any]:
    return {
        "id": goal_id,
        "claim": claim,
        "status": status,
        "severity": severity or DEFAULT_GOAL_SEVERITY.get(status, "warning"),
        "reason": reason,
        "dependencies": dependencies,
    }


ThresholdReason = str | Callable[[float, float], str]
ThresholdDependencies = list[str] | dict[str, list[str]]

_THRESHOLD_OPERATORS = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def _threshold_reason(template: ThresholdReason, value: float, limit: float) -> str:
    if callable(template):
        return template(value, limit)
    return str(template).format(value=value, limit=limit)


def _threshold_dependencies(
    dependencies: ThresholdDependencies, state: str
) -> list[str]:
    if isinstance(dependencies, list):
        return dependencies
    if isinstance(dependencies, dict):
        selected = dependencies.get(state, dependencies.get("default", []))
        if isinstance(selected, list):
            return selected
    return []


def threshold_goal(
    goal_id: str,
    claim: str,
    value: float | None,
    op: str,
    limit: float | None,
    dependencies: ThresholdDependencies,
    *,
    open_reason: str,
    templates: dict[str, ThresholdReason],
    open_status: str = "open",
    open_severity: str = "warning",
    closed_status: str = "closed",
    closed_severity: str = "soft",
    failed_status: str = "failed",
    failed_severity: str = "hard",
) -> dict[str, Any]:
    comparator = _THRESHOLD_OPERATORS.get(op)
    if comparator is None:
        raise ValueError(f"unsupported threshold operator: {op}")
    if value is None or limit is None:
        return goal(
            goal_id,
            claim,
            open_status,
            open_reason,
            _threshold_dependencies(dependencies, "open"),
            severity=open_severity,
        )
    if comparator(value, limit):
        return goal(
            goal_id,
            claim,
            closed_status,
            _threshold_reason(templates["closed"], value, limit),
            _threshold_dependencies(dependencies, "closed"),
            severity=closed_severity,
        )
    return goal(
        goal_id,
        claim,
        failed_status,
        _threshold_reason(templates["failed"], value, limit),
        _threshold_dependencies(dependencies, "failed"),
        severity=failed_severity,
    )


def has_failed_goal(
    goals: Iterable[dict[str, Any]],
    *,
    severity: str | None = None,
    ids: set[str] | None = None,
    claims: set[str] | None = None,
) -> bool:
    for item in goals:
        if item.get("status") != "failed":
            continue
        if severity is not None and item.get("severity") != severity:
            continue
        if ids is not None and item.get("id") not in ids:
            continue
        if claims is not None and item.get("claim") not in claims:
            continue
        return True
    return False


def raw_variable_value(ir: dict[str, Any], name: str) -> Any:
    variable = ir.get("variables", {}).get(name, {})
    if isinstance(variable, dict):
        return variable.get("value")
    return None


def text_variable_value(ir: dict[str, Any], name: str) -> str | None:
    raw = raw_variable_value(ir, name)
    if raw is None:
        return None
    return str(raw).strip().lower()


def numeric_mapping_value(
    mapping: dict[str, Any], name: str, default: float | None = None
) -> float | None:
    item = mapping.get(name)
    if not isinstance(item, dict):
        return default
    raw = item.get("value")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def numeric_ir_value(
    ir: dict[str, Any], name: str, default: float | None = None
) -> float | None:
    return numeric_mapping_value(ir.get("variables", {}), name, default)


def round_or_none(value: Any, ndigits: int = 2) -> float | None:
    """Round numbers, pass ``None`` through. Keeps derived-value dicts readable."""
    return round(value, ndigits) if isinstance(value, (int, float)) else None


def applied_defaults(ir: dict[str, Any], defaults: dict[str, Any]) -> dict[str, float]:
    """Defaults that silently shaped the result because the IR omitted them.

    Only counts variables fully absent from the IR. An explicit null (status
    ``unknown``) is a disclosed unknown that opens a goal, not a silent default,
    so it is deliberately excluded.
    """
    variables = ir.get("variables", {})
    if not isinstance(variables, dict):
        return {}
    return {
        name: float(value) for name, value in defaults.items() if name not in variables
    }


def boolish(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    normalized = str(raw).strip().lower()
    if normalized in {"yes", "true", "1"}:
        return True
    if normalized in {"no", "false", "0"}:
        return False
    return None


def evidence_quality_from_records(records: Iterable[dict[str, Any]]) -> str:
    confidences = []
    has_weak_source = False
    for record in records:
        if not isinstance(record, dict):
            continue
        source = record.get("source")
        confidence = record.get("confidence")
        if source in WEAK_SOURCES:
            has_weak_source = True
        if isinstance(confidence, (int, float)):
            confidences.append(float(confidence))
    if has_weak_source or (confidences and min(confidences) < 0.5):
        return "weak"
    if confidences and min(confidences) >= 0.75:
        return "strong"
    return "medium"


def evidence_quality_from_variables(ir: dict[str, Any], names: list[str]) -> str:
    variables = ir.get("variables", {})
    return evidence_quality_from_records(variables.get(name, {}) for name in names)


def recommendation_status(
    *,
    hard_failed: bool,
    open_required: bool,
    positive_case: bool,
    evidence_quality: str,
    baseline: bool = False,
    caution_failed: bool = False,
) -> str:
    """Map proof state to a recommendation.

    ``caution_failed`` is for warning-severity failed goals (a real but
    non-fatal breach, e.g. a cost above the comfort threshold but below the
    hard ceiling). It cannot coexist with a positive recommendation: the best
    it allows is ``lean_no``, so guidance that says "this is unsafe" never sits
    next to a recommend/lean_yes conclusion.
    """
    if baseline:
        return "baseline"
    if hard_failed:
        return "do_not_recommend"
    if open_required:
        return "insufficient_evidence"
    if caution_failed:
        return "lean_no"
    if positive_case and evidence_quality == "strong":
        return "recommend"
    if positive_case:
        return "lean_yes"
    return "lean_no"


def error_payload(error: Exception | str) -> dict[str, Any]:
    return {"ok": False, "error": str(error)}
