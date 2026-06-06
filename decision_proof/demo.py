"""Repository-first demo entrypoints for Decision Proof."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_proof.report import load_json, make_run, render_markdown
from decision_proof.runtime import next_questions

ROOT = Path(__file__).resolve().parents[1]


def car_options_demo() -> dict[str, Any]:
    ir_path = ROOT / "examples" / "car-options-comparison.json"
    ir = load_json(ir_path)
    run = make_run(ir, ir_path, "demo_car_options")
    return {
        "demo": "car-options",
        "decision_id": run["decision_id"],
        "best_option": run.get("recommendation", {}).get("best_option"),
        "ranking": run.get("comparison", {}).get("ranking", []),
        "options": [
            {
                "id": option.get("id"),
                "label": option.get("label"),
                "status": option.get("status"),
                "main_risk": option.get("main_risk"),
            }
            for option in run.get("comparison", {}).get("options", [])
            if isinstance(option, dict)
        ],
        "next_questions": next_questions(ir),
        "run": run,
        "markdown_report": render_markdown(run),
    }
