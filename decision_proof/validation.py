"""Decision IR validation helpers."""

from __future__ import annotations

import json
from pathlib import Path

from decision_proof.core.domain_runtime import validation_errors
from decision_proof.core.schema_validation import validate_instance


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(ir: dict) -> list[str]:
    errors: list[str] = validate_instance(ir, "decision_ir.schema.json")

    variables = ir.get("variables", {}) if isinstance(ir.get("variables"), dict) else {}

    for name, variable in variables.items():
        if not isinstance(variable, dict):
            continue
        if variable.get("value") is None and variable.get("status") != "unknown":
            errors.append(f"variables.{name}.status must be 'unknown' when value is null")

    rules = ir.get("rules", [])
    if rules and not isinstance(rules, list):
        errors.append("rules must be a list")
    elif isinstance(rules, list):
        variable_names = set(variables.keys())
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                errors.append(f"rules[{index}] must be an object")
                continue
            for dep in rule.get("dependencies", []):
                if dep not in variable_names:
                    errors.append(f"rules[{index}] dependency not found in variables: {dep}")

    errors.extend(validation_errors(ir))
    return sorted(set(errors))


__all__ = ["load_json", "validate"]