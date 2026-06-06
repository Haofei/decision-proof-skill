"""Load domain metadata from package-managed domain manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DomainSpec:
    key: str
    decision_types: tuple[str, ...]
    required_variables: tuple[str, ...]
    summary: str | None
    verifier: str | None
    module_name: str
    module_path: Path
    model_path: Path


def load_manifest_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def domain_manifest(path: Path) -> dict[str, Any]:
    return load_manifest_json(path)


def _domain_root() -> Path:
    return PACKAGE_ROOT / "domains"


@lru_cache(maxsize=1)
def domain_specs() -> tuple[DomainSpec, ...]:
    specs: list[DomainSpec] = []
    seen: set[str] = set()
    root = _domain_root()
    if not root.exists():
        return tuple()
    for domain_dir in sorted(root.glob("*/")):
        manifest_path = domain_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        metadata = load_manifest_json(manifest_path)
        key = str(metadata.get("key") or domain_dir.name).strip()
        if key in seen:
            continue
        seen.add(key)
        entry_point = str(metadata.get("entry_point") or "domain.py")
        module_path = domain_dir / entry_point
        module_name = ".".join(
            module_path.relative_to(PACKAGE_ROOT.parent).with_suffix("").parts
        )
        specs.append(
            DomainSpec(
                key=key,
                decision_types=tuple(
                    str(item) for item in metadata.get("decision_types", [])
                ),
                required_variables=tuple(
                    str(item) for item in metadata.get("required_variables", [])
                ),
                summary=str(metadata.get("summary"))
                if metadata.get("summary") is not None
                else None,
                verifier=str(metadata.get("verifier"))
                if metadata.get("verifier") is not None
                else None,
                module_name=module_name,
                module_path=module_path,
                model_path=manifest_path,
            )
        )
    return tuple(specs)
