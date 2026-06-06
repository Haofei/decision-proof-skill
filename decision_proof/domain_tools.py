"""Domain-pack tooling.

Pack-level (not run-level) commands: validate a pack's manifest against the
manifest schema, and run its golden cases. These enforce the acceptance bar in
``references/domain-pack-contract.md`` so the platform protocol is executable,
not just documented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decision_proof.core.domain_metadata import load_manifest_json
from decision_proof.core.schema_validation import validate_instance
from decision_proof.report import make_run

MIN_GOLDEN_CASES = 3


def _golden_paths(domain_dir: Path) -> list[Path]:
    golden_dir = domain_dir / "golden"
    return sorted(golden_dir.glob("*.json")) if golden_dir.exists() else []


def validate_domain(domain_dir: Path, *, strict: bool = False) -> dict[str, Any]:
    """Schema-validate the manifest and check structural pack requirements.

    In dev mode (default) the contract quality bar is reported as warnings so a
    pack can be built up to it. In ``strict`` mode (release / registry gate) the
    warnings become hard errors.
    """
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = domain_dir / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "errors": [f"missing manifest.json in {domain_dir}"]}
    try:
        manifest = load_manifest_json(manifest_path)
    except json.JSONDecodeError as exc:
        return {"ok": False, "errors": [f"manifest.json is not valid JSON: {exc}"]}

    errors.extend(validate_instance(manifest, "domain_manifest.schema.json"))

    entry_point = str(manifest.get("entry_point", "domain.py"))
    if not (domain_dir / entry_point).exists():
        errors.append(f"entry_point '{entry_point}' not found")

    # Contract quality bar.
    golden = _golden_paths(domain_dir)
    if len(golden) < MIN_GOLDEN_CASES:
        warnings.append(
            f"contract requires >= {MIN_GOLDEN_CASES} golden cases; found {len(golden)}"
        )

    if strict:
        errors.extend(warnings)
        warnings = []

    return {
        "ok": not errors,
        "strict": strict,
        "errors": errors,
        "warnings": warnings,
        "golden_cases": len(golden),
    }


def test_domain(domain_dir: Path) -> dict[str, Any]:
    """Run every golden case and check it reproduces its expected outcome."""
    golden = _golden_paths(domain_dir)
    cases: list[dict[str, Any]] = []

    for path in golden:
        spec = load_manifest_json(path)
        ir = spec.get("ir", {})
        expect = spec.get("expect", {})
        run = make_run(ir, path, f"golden_{path.stem}")

        failures: list[str] = []
        actual_status = run["recommendation"]["status"]
        expected_status = expect.get("recommendation_status")
        if expected_status is not None and actual_status != expected_status:
            failures.append(
                f"recommendation_status {actual_status!r} != {expected_status!r}"
            )
        for key, value in expect.get("derived_values", {}).items():
            actual = run["derived_values"].get(key)
            if actual != value:
                failures.append(f"derived_values.{key} {actual!r} != {value!r}")
        if not run["global_verifier_result"]["ok"]:
            failures.append("global invariants failed")

        cases.append(
            {
                "name": spec.get("name", path.stem),
                "ok": not failures,
                "failures": failures,
            }
        )

    ok = bool(cases) and all(case["ok"] for case in cases)
    return {"ok": ok, "count": len(cases), "cases": cases}
