#!/usr/bin/env python3
"""Validate a Decision IR JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_TOP_LEVEL = ["decision", "options", "variables"]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(ir: dict) -> list[str]:
    errors: list[str] = []

    for key in REQUIRED_TOP_LEVEL:
        if key not in ir:
            errors.append(f"missing top-level key: {key}")

    decision = ir.get("decision", {})
    if not isinstance(decision, dict):
        errors.append("decision must be an object")
    else:
        for key in ["id", "question", "type"]:
            if not decision.get(key):
                errors.append(f"decision.{key} is required")

    options = ir.get("options", [])
    if not isinstance(options, list) or len(options) < 2:
        errors.append("options must contain at least two options")
    else:
        seen = set()
        for index, option in enumerate(options):
            if not isinstance(option, dict):
                errors.append(f"options[{index}] must be an object")
                continue
            option_id = option.get("id")
            if not option_id:
                errors.append(f"options[{index}].id is required")
            elif option_id in seen:
                errors.append(f"duplicate option id: {option_id}")
            seen.add(option_id)

    variables = ir.get("variables", {})
    if not isinstance(variables, dict):
        errors.append("variables must be an object")
    else:
        for name, variable in variables.items():
            if not isinstance(variable, dict):
                errors.append(f"variables.{name} must be an object")
                continue
            if "value" not in variable:
                errors.append(f"variables.{name}.value is required")
            if "unit" not in variable:
                errors.append(f"variables.{name}.unit is required, use null if dimensionless")
            confidence = variable.get("confidence")
            if confidence is None:
                errors.append(f"variables.{name}.confidence is required")
            elif not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                errors.append(f"variables.{name}.confidence must be between 0 and 1")
            if not variable.get("source"):
                errors.append(f"variables.{name}.source is required")

    rules = ir.get("rules", [])
    if rules and not isinstance(rules, list):
        errors.append("rules must be a list")
    elif isinstance(rules, list):
        variable_names = set(ir.get("variables", {}).keys()) if isinstance(ir.get("variables"), dict) else set()
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                errors.append(f"rules[{index}] must be an object")
                continue
            for dep in rule.get("dependencies", []):
                if dep not in variable_names:
                    errors.append(f"rules[{index}] dependency not found in variables: {dep}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Decision IR JSON file.")
    parser.add_argument("ir_json", type=Path)
    args = parser.parse_args()

    try:
        ir = load_json(args.ir_json)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
        return 1

    errors = validate(ir)
    print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
