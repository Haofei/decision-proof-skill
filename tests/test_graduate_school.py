from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


report_mod = load_module("generate_report", ROOT / "scripts" / "generate_report.py")
runtime_mod = load_module("domain_runtime", ROOT / "core" / "domain_runtime.py")
validate_mod = load_module("validate_ir", ROOT / "scripts" / "validate_ir.py")


class GraduateSchoolTests(unittest.TestCase):
    def test_runtime_detects_graduate_school_domain(self):
        ir = report_mod.load_json(ROOT / "examples" / "graduate-school-decision.json")

        self.assertEqual(runtime_mod.domain_key(ir), "graduate_school")

        result = runtime_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "do_not_recommend")
        self.assertEqual(result["derived_values"]["payback_years_after_graduation"], 5.2)

    def test_report_renders_graduate_school_run(self):
        ir_path = ROOT / "examples" / "graduate-school-decision.json"
        ir = report_mod.load_json(ir_path)

        run = report_mod.make_run(ir, ir_path, "grad_test")
        markdown = report_mod.render_markdown(run)

        self.assertEqual(run["domain"], "graduate_school")
        self.assertEqual(run["recommendation"]["status"], "do_not_recommend")
        self.assertIn("`payback_years_after_graduation`: 5.2", markdown)
        self.assertIn("Verification: OPEN", markdown)
        self.assertIn("## Decision Guidance", markdown)
        self.assertIn("funding-path problem", run["guidance"]["summary"])
        self.assertIn("$50,000", run["guidance"]["focus"])
        self.assertIn("$186,667/year", run["guidance"]["next_step"])

    def test_negative_salary_premium_stays_hard_fail(self):
        ir = report_mod.load_json(ROOT / "examples" / "graduate-school-decision.json")
        ir["variables"]["post_grad_expected_salary"]["value"] = 90000
        ir["variables"]["risk_tolerance"]["value"] = "medium"
        ir["variables"]["savings"]["value"] = 70000
        ir["variables"]["loan_required"]["value"] = "no"

        result = runtime_mod.evaluate(ir)
        goal_map = {goal["claim"]: goal for goal in result["proof_state"]["goals"]}

        self.assertEqual(goal_map["salary_premium_positive"]["status"], "failed")
        self.assertEqual(goal_map["salary_premium_positive"]["severity"], "hard")
        self.assertEqual(goal_map["payback_within_risk_window"]["status"], "open")
        self.assertEqual(result["recommendation"]["status"], "do_not_recommend")

    def test_runtime_metadata_comes_from_model_yaml(self):
        ir = report_mod.load_json(ROOT / "examples" / "graduate-school-decision.json")

        spec = runtime_mod.resolve_domain_spec(ir)

        self.assertEqual(spec.key, "graduate_school")
        self.assertEqual(
            spec.required_variables,
            ("study_years", "annual_tuition_living_cost", "direct_work_salary", "post_grad_expected_salary"),
        )

    def test_validator_uses_graduate_model_required_variables(self):
        ir = report_mod.load_json(ROOT / "examples" / "graduate-school-decision.json")
        del ir["variables"]["direct_work_salary"]

        errors = validate_mod.validate(ir)

        self.assertTrue(any("missing required variables for domain 'graduate_school'" in error for error in errors))
        self.assertTrue(any("direct_work_salary" in error for error in errors))

    def test_evaluate_decision_returns_clean_unknown_domain_error(self):
        ir = report_mod.load_json(ROOT / "examples" / "graduate-school-decision.json")
        ir["decision"]["type"] = "mystery_domain"

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(ir, handle)
            path = handle.name

        proc = subprocess.run(
            ["python3", str(ROOT / "scripts" / "evaluate_decision.py"), path],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("unsupported decision domain/type", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()