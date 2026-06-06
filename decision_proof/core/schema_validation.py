"""JSON Schema loading and validation helpers."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from datetime import datetime
except ImportError:  # pragma: no cover
    datetime = None


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = ROOT / "schemas"


def schema_path(schema_name: str) -> Path:
    return SCHEMAS_DIR / schema_name


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, Any]:
    with schema_path(schema_name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=None)
def _draft_validator():
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError:
        return None
    return Draft202012Validator


@lru_cache(maxsize=None)
def validator_for(schema_name: str):
    draft_validator = _draft_validator()
    if draft_validator is None:
        return None
    return draft_validator(load_schema(schema_name))


def _matches_type(instance: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(instance, dict)
    if expected_type == "array":
        return isinstance(instance, list)
    if expected_type == "string":
        return isinstance(instance, str)
    if expected_type == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected_type == "boolean":
        return isinstance(instance, bool)
    if expected_type == "null":
        return instance is None
    return True


def _type_label(instance: Any) -> str:
    if instance is None:
        return "null"
    if isinstance(instance, bool):
        return "boolean"
    if isinstance(instance, dict):
        return "object"
    if isinstance(instance, list):
        return "array"
    if isinstance(instance, str):
        return "string"
    if isinstance(instance, (int, float)):
        return "number"
    return type(instance).__name__


def _unique_key(instance: Any) -> str:
    return json.dumps(instance, sort_keys=True, separators=(",", ":"), default=str)


def _schema_matches(instance: Any, schema: dict[str, Any]) -> bool:
    errors: list[str] = []
    _validate_locally(instance, schema, "$", errors)
    return not errors


def _validate_locally(
    instance: Any, schema: dict[str, Any], location: str, errors: list[str]
) -> None:
    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(_matches_type(instance, item) for item in expected_type):
            errors.append(
                f"{location}: {_type_label(instance)} is not of type {expected_type}"
            )
            return
    elif isinstance(expected_type, str) and not _matches_type(instance, expected_type):
        errors.append(
            f"{location}: {_type_label(instance)} is not of type '{expected_type}'"
        )
        return

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{location}: {instance!r} is not one of {schema['enum']}")
    if "const" in schema and instance != schema["const"]:
        errors.append(
            f"{location}: {instance!r} was expected to be {schema['const']!r}"
        )

    if isinstance(instance, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(instance) < min_length:
            errors.append(
                f"{location}: string is shorter than minimum length {min_length}"
            )
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.match(pattern, instance) is None:
            errors.append(
                f"{location}: {instance!r} does not match pattern {pattern!r}"
            )
        if schema.get("format") == "date-time" and datetime is not None:
            try:
                datetime.fromisoformat(instance.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{location}: {instance!r} is not a 'date-time'")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and instance < minimum:
            errors.append(
                f"{location}: {instance} is less than the minimum of {minimum}"
            )
        if isinstance(maximum, (int, float)) and instance > maximum:
            errors.append(
                f"{location}: {instance} is greater than the maximum of {maximum}"
            )

    if "if" in schema and _schema_matches(instance, schema["if"]):
        then_schema = schema.get("then")
        if isinstance(then_schema, dict):
            _validate_locally(instance, then_schema, location, errors)

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{location}: {key!r} is a required property")

        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in instance and isinstance(subschema, dict):
                child_location = f"{location}.{key}" if location != "$" else key
                _validate_locally(instance[key], subschema, child_location, errors)

        additional = schema.get("additionalProperties", True)
        extras = [key for key in instance.keys() if key not in properties]
        if additional is False:
            for key in extras:
                errors.append(f"{location}: additional property {key!r} is not allowed")
        elif isinstance(additional, dict):
            for key in extras:
                child_location = f"{location}.{key}" if location != "$" else key
                _validate_locally(instance[key], additional, child_location, errors)

    if isinstance(instance, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            errors.append(f"{location}: array has too few items")
        if schema.get("uniqueItems"):
            seen: set[str] = set()
            for item in instance:
                marker = _unique_key(item)
                if marker in seen:
                    errors.append(f"{location}: array items are not unique")
                    break
                seen.add(marker)
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                child_location = (
                    f"{location}.{index}" if location != "$" else str(index)
                )
                _validate_locally(item, item_schema, child_location, errors)


def validate_instance(instance: Any, schema_name: str) -> list[str]:
    validator = validator_for(schema_name)
    if validator is not None:
        errors = []
        for error in sorted(
            validator.iter_errors(instance),
            key=lambda item: [str(part) for part in item.absolute_path],
        ):
            location = ".".join(str(part) for part in error.absolute_path) or "$"
            errors.append(f"{schema_name}:{location}: {error.message}")
        return errors

    local_errors: list[str] = []
    _validate_locally(instance, load_schema(schema_name), "$", local_errors)
    return [f"{schema_name}:{error}" for error in local_errors]
