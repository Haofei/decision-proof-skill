from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from decision_proof.core import domain_runtime as runtime_mod
from decision_proof.report import load_json, make_run, render_markdown
from decision_proof.validation import validate as validate_ir

ROOT = Path(__file__).resolve().parents[1]


class GraduateSchoolTests(unittest.TestCase):
    def test_runtime_detects_graduate_school_domain(self):
        ir = load_json(ROOT / "examples" / "graduate-school-decision.json")

        self.assertEqual(runtime_mod.domain_key(ir), "graduate_school")

        result = runtime_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "do_not_recommend")
        self.assertEqual(
            result["derived_values"]["payback_years_after_graduation"], 5.2
        )

    def test_report_renders_graduate_school_run(self):
        ir_path = ROOT / "examples" / "graduate-school-decision.json"
        ir = load_json(ir_path)

        run = make_run(ir, ir_path, "grad_test")
        markdown = render_markdown(run)

        self.assertEqual(run["domain"], "graduate_school")
        self.assertEqual(run["recommendation"]["status"], "do_not_recommend")
        self.assertIn("`payback_years_after_graduation`: 5.2", markdown)
        self.assertIn(
            "Verification: PASS: Rule closure checked (GraduateSchoolDeterministicInvariants)",
            markdown,
        )
        self.assertIn("## Decision Guidance", markdown)
        self.assertIn("funding-path problem", run["guidance"]["summary"])
        self.assertIn("$50,000", run["guidance"]["focus"])
        self.assertIn("$186,667/year", run["guidance"]["next_step"])

    def test_report_discloses_default_risk_window_assumption(self):
        ir_path = ROOT / "examples" / "graduate-school-decision.json"
        ir = load_json(ir_path)

        run = make_run(ir, ir_path, "grad_assume")
        markdown = render_markdown(run)

        # risk_tolerance is "low" and the example omits the window prior.
        self.assertEqual(
            run["assumptions_used"], {"target_payback_years_low_risk": 3.0}
        )
        self.assertIn("## Default Assumptions (priors)", markdown)
        self.assertIn("`target_payback_years_low_risk`: 3", markdown)

    def test_domain_verifier_passes_on_example(self):
        from decision_proof.domains.graduate_school import domain as domain_mod

        result = domain_mod.verify(ROOT / "examples" / "graduate-school-decision.json")

        self.assertTrue(result["proof_checked"])
        self.assertEqual(result["failed_checks"], [])
        self.assertIn("do_not_recommend_requires_hard_fail", result["passed_checks"])

    def test_negative_salary_premium_stays_hard_fail(self):
        ir = load_json(ROOT / "examples" / "graduate-school-decision.json")
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

    def test_runtime_metadata_comes_from_manifest(self):
        ir = load_json(ROOT / "examples" / "graduate-school-decision.json")

        spec = runtime_mod.resolve_domain_spec(ir)

        self.assertEqual(spec.key, "graduate_school")
        self.assertEqual(spec.model_path.name, "manifest.json")
        self.assertEqual(
            spec.required_variables,
            (
                "study_years",
                "annual_tuition_living_cost",
                "direct_work_salary",
                "post_grad_expected_salary",
            ),
        )

    def test_validator_uses_graduate_model_required_variables(self):
        ir = load_json(ROOT / "examples" / "graduate-school-decision.json")
        del ir["variables"]["direct_work_salary"]

        errors = validate_ir(ir)

        self.assertTrue(
            any(
                "missing required variables for domain 'graduate_school'" in error
                for error in errors
            )
        )
        self.assertTrue(any("direct_work_salary" in error for error in errors))

    def test_evaluate_decision_returns_clean_unknown_domain_error(self):
        ir = load_json(ROOT / "examples" / "graduate-school-decision.json")
        ir["decision"]["type"] = "mystery_domain"

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(ir, handle)
            path = handle.name

        proc = subprocess.run(
            ["python3", "-m", "decision_proof.cli", "evaluate", path],
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
