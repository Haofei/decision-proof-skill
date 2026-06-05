"""Shared helpers for domain evaluators and runtime entrypoints."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Iterable


WEAK_SOURCES = {"guessed", "unknown"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def goal(goal_id: str, claim: str, status: str, reason: str, dependencies: list[str]) -> dict[str, Any]:
    return {
        "id": goal_id,
        "claim": claim,
        "status": status,
        "reason": reason,
        "dependencies": dependencies,
    }


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


def numeric_mapping_value(mapping: dict[str, Any], name: str, default: float | None = None) -> float | None:
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


def numeric_ir_value(ir: dict[str, Any], name: str, default: float | None = None) -> float | None:
    return numeric_mapping_value(ir.get("variables", {}), name, default)


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
) -> str:
    if baseline:
        return "baseline"
    if hard_failed:
        return "do_not_recommend"
    if open_required:
        return "insufficient_evidence"
    if positive_case and evidence_quality == "strong":
        return "recommend"
    if positive_case:
        return "lean_yes"
    return "lean_no"


def error_payload(error: Exception | str) -> dict[str, Any]:
    return {"ok": False, "error": str(error)}
