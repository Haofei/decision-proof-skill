#!/usr/bin/env python3
"""Generate a Decision Proof report and run artifact from a Decision IR JSON file."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


evaluate_mod = load_module("evaluate_car_decision", ROOT / "scripts" / "evaluate_car_decision.py")
sensitivity_mod = load_module("sensitivity", ROOT / "scripts" / "sensitivity.py")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def variable_rows(ir: dict[str, Any], proof_state: dict[str, Any]) -> list[dict[str, Any]]:
    used_in: dict[str, list[str]] = {}
    for goal in proof_state.get("goals", []):
        for dependency in goal.get("dependencies", []):
            used_in.setdefault(dependency, []).append(goal.get("claim", "unknown_goal"))

    rows = []
    for name, variable in sorted(ir.get("variables", {}).items()):
        if not isinstance(variable, dict):
            continue
        value = variable.get("value")
        rows.append(
            {
                "name": name,
                "value": "unknown" if value is None else value,
                "unit": variable.get("unit"),
                "source": variable.get("source"),
                "confidence": variable.get("confidence"),
                "status": variable.get("status") or ("unknown" if value is None else "known"),
                "used_in": sorted(set(used_in.get(name, []))),
            }
        )
    return rows


def run_lean_if_possible(ir_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="decision-proof-report-") as tempdir:
        lean_path = Path(tempdir) / "CarDecisionProof.lean"
        proc = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts" / "generate_lean_car_proof.py"),
                str(ir_path),
                "--out",
                str(lean_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": proc.stderr or proc.stdout}
        parsed["returncode"] = proc.returncode
        return parsed


def make_run(ir: dict[str, Any], ir_path: Path, run_id: str | None = None) -> dict[str, Any]:
    evaluation = evaluate_mod.evaluate(ir)
    sensitivity = sensitivity_mod.thresholds(ir)
    verifier = run_lean_if_possible(ir_path)
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    decision_id = ir.get("decision", {}).get("id", "decision")

    return {
        "run_id": run_id or f"run_{created_at}",
        "decision_id": decision_id,
        "created_at": created_at,
        "input_ir_hash": canonical_hash(ir),
        "input_ir": ir,
        "derived_values": evaluation["derived_values"],
        "proof_state": evaluation["proof_state"],
        "recommendation": evaluation["recommendation"],
        "sensitivity": sensitivity,
        "verifier_result": verifier,
    }


def format_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def goal_mark(status: str) -> str:
    return {
        "closed": "PASS",
        "failed": "FAIL",
        "open": "OPEN",
        "assumption": "ASSUME",
    }.get(status, status.upper())


def verifier_badge(verifier: dict[str, Any]) -> str:
    if verifier.get("proof_checked"):
        return f"PASS: Rule closure checked ({verifier.get('proved_predicate')})"
    return f"OPEN: Not proof-checked ({verifier.get('error', 'verifier incomplete')})"


def render_markdown(run: dict[str, Any]) -> str:
    ir = run["input_ir"]
    decision = ir.get("decision", {})
    recommendation = run["recommendation"]
    derived = run["derived_values"]
    proof_state = run["proof_state"]
    sensitivity = run["sensitivity"]
    variables = variable_rows(ir, proof_state)

    lines = [
        f"# Decision Report: {decision.get('question', decision.get('id', 'Untitled decision'))}",
        "",
        "## Current Conclusion",
        "",
        f"- Status: `{recommendation.get('status')}`",
        f"- Evidence quality: `{recommendation.get('evidence_quality')}`",
        f"- Verification: {verifier_badge(run.get('verifier_result', {}))}",
        "",
        "## Key Derived Values",
        "",
    ]

    for key, value in derived.items():
        lines.append(f"- `{key}`: {format_value(value)}")

    lines.extend(["", "## Flip Conditions", ""])
    for key, value in sensitivity.get("flip_conditions", {}).items():
        lines.append(f"- `{key}`: {format_value(value)}")

    unknowns = sensitivity.get("current", {}).get("unknown_variables", [])
    if unknowns:
        lines.extend(["", "## Unknown Variables Affecting Sensitivity", ""])
        for name in unknowns:
            lines.append(f"- `{name}`")

    lines.extend(["", "## Proof Goals", ""])
    for proof_goal in proof_state.get("goals", []):
        lines.append(
            f"- {goal_mark(proof_goal.get('status', 'unknown'))}: `{proof_goal.get('claim')}` - {proof_goal.get('reason')}"
        )

    lines.extend(
        [
            "",
            "## Variables / Evidence Table",
            "",
            "| Variable | Value | Unit | Source | Confidence | Status | Used In |",
            "| --- | ---: | --- | --- | ---: | --- | --- |",
        ]
    )
    for row in variables:
        used_in = ", ".join(row["used_in"]) if row["used_in"] else ""
        lines.append(
            f"| `{row['name']}` | {format_value(row['value'])} | {format_value(row['unit'])} | "
            f"{format_value(row['source'])} | {format_value(row['confidence'])} | {format_value(row['status'])} | {used_in} |"
        )

    open_goals = [goal for goal in proof_state.get("goals", []) if goal.get("status") in {"open", "assumption"}]
    if open_goals:
        lines.extend(["", "## Next Evidence", ""])
        seen = set()
        for proof_goal in open_goals:
            for dependency in proof_goal.get("dependencies", []):
                if dependency in seen:
                    continue
                seen.add(dependency)
                lines.append(f"- Clarify `{dependency}` for `{proof_goal.get('claim')}`.")

    lines.extend(["", f"_Run: `{run['run_id']}`. Input hash: `{run['input_ir_hash']}`._", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Decision Proof report.")
    parser.add_argument("ir_json", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args()

    ir = load_json(args.ir_json)
    run = make_run(ir, args.ir_json, args.run_id)
    markdown = render_markdown(run)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(run, indent=2), encoding="utf-8")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(markdown, encoding="utf-8")
    if not args.json_out and not args.md_out:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
