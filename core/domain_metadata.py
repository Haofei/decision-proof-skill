"""Load domain metadata from domains/*/model.yaml."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DomainSpec:
    key: str
    decision_types: tuple[str, ...]
    required_variables: tuple[str, ...]
    summary: str | None
    verifier: str | None
    module_path: Path
    model_path: Path


def parse_scalar(value: str) -> Any:
    stripped = value.strip()
    if stripped in {"null", "None"}:
        return None
    if stripped == "true":
        return True
    if stripped == "false":
        return False
    return stripped


def load_model_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  - "):
            if current_list is None or not isinstance(data.get(current_list), list):
                raise ValueError(f"invalid list item in {path}: {raw_line}")
            data[current_list].append(parse_scalar(line[4:]))
            continue
        if line.startswith(" "):
            raise ValueError(f"unsupported nested mapping in {path}: {raw_line}")

        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"invalid yaml line in {path}: {raw_line}")

        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = []
            current_list = key
        else:
            data[key] = parse_scalar(value)
            current_list = None

    return data


def load_manifest_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def domain_specs() -> tuple[DomainSpec, ...]:
    specs = []
    for domain_dir in sorted((ROOT / "domains").glob("*/")):
        manifest_path = domain_dir / "manifest.json"
        model_path = domain_dir / "model.yaml"
        if manifest_path.exists():
            metadata = load_manifest_json(manifest_path)
            metadata_path = manifest_path
        elif model_path.exists():
            metadata = load_model_yaml(model_path)
            metadata_path = model_path
        else:
            continue
        entry_point = str(metadata.get("entry_point") or "domain.py")
        specs.append(
            DomainSpec(
                key=str(metadata.get("key") or domain_dir.name).strip(),
                decision_types=tuple(str(item) for item in metadata.get("decision_types", [])),
                required_variables=tuple(str(item) for item in metadata.get("required_variables", [])),
                summary=str(metadata.get("summary")) if metadata.get("summary") is not None else None,
                verifier=str(metadata.get("verifier")) if metadata.get("verifier") is not None else None,
                module_path=domain_dir / entry_point,
                model_path=metadata_path,
            )
        )
    return tuple(specs)