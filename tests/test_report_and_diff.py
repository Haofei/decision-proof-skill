from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


report_mod = load_module("generate_report", ROOT / "scripts" / "generate_report.py")
diff_mod = load_module("diff_runs", ROOT / "scripts" / "diff_runs.py")


class ReportAndDiffTests(unittest.TestCase):
    def test_report_contains_workspace_sections(self):
        ir_path = ROOT / "examples" / "car-decision.json"
        ir = report_mod.load_json(ir_path)

        run = report_mod.make_run(ir, ir_path, "test_run")
        markdown = report_mod.render_markdown(run)

        self.assertIn("## Current Conclusion", markdown)
        self.assertIn("## Decision Guidance", markdown)
        self.assertIn("## Variables / Evidence Table", markdown)
        self.assertIn("Verification: OPEN", markdown)
        self.assertIn("`value_of_time` | unknown", markdown)

    def test_car_report_guidance_prioritizes_decision_defining_unknown(self):
        ir_path = ROOT / "examples" / "car-decision.json"
        ir = report_mod.load_json(ir_path)

        run = report_mod.make_run(ir, ir_path, "guided_run")
        markdown = report_mod.render_markdown(run)

        self.assertIn("$62.5/hour", run["guidance"]["focus"])
        self.assertIn("Emergency-fund safety and income affordability already pass", run["guidance"]["deprioritize"])
        self.assertIn("Do not force a conclusion yet", markdown)
        self.assertIn("what one regained hour is actually worth", markdown)

    def test_option_comparison_report_uses_core_runtime(self):
        ir_path = ROOT / "examples" / "car-options-comparison.json"
        ir = report_mod.load_json(ir_path)

        run = report_mod.make_run(ir, ir_path, "options_run")
        markdown = report_mod.render_markdown(run)

        self.assertEqual(run["recommendation"]["best_option"], "used_gas_car")
        self.assertEqual(run["domain"], "car")
        self.assertIn("## Option Ranking", markdown)
        self.assertIn("used_gas_car", markdown)
        self.assertIn("Best actionable option is Used gas car", markdown)

    def test_diff_reports_recommendation_and_variable_changes(self):
        from_path = ROOT / "examples" / "car-decision.json"
        to_path = ROOT / "examples" / "car-decision-value-time-100.json"

        from_run = report_mod.make_run(report_mod.load_json(from_path), from_path, "from")
        to_run = report_mod.make_run(report_mod.load_json(to_path), to_path, "to")
        diff = diff_mod.diff_runs(from_run, to_run)

        self.assertEqual(diff["recommendation_change"]["from"], "insufficient_evidence")
        self.assertEqual(diff["recommendation_change"]["to"], "lean_yes")
        self.assertEqual(diff["variable_changes"]["value_of_time"], {"from": None, "to": 100})
        self.assertEqual(
            diff["proof_goal_changes"]["benefit_exceeds_incremental_cost"]["status_to"],
            "closed",
        )


if __name__ == "__main__":
    unittest.main()
