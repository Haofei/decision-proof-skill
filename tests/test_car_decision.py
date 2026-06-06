from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from decision_proof.domains.car import evaluator as evaluate_mod
from decision_proof.domains.car import verifier as verifier_mod
from decision_proof.validation import validate as validate_ir

ROOT = Path(__file__).resolve().parents[1]


def base_ir() -> dict:
    return {
        "decision": {
            "id": "test_car",
            "question": "Should I buy a car?",
            "type": "personal_finance_mobility",
        },
        "options": [
            {"id": "buy_car", "label": "Buy a car"},
            {"id": "no_car", "label": "Do not buy a car"},
        ],
        "variables": {
            "commute_days_per_month": {
                "value": 20,
                "unit": "days/month",
                "confidence": 0.8,
                "source": "measured",
            },
            "current_minutes_each_way": {
                "value": 60,
                "unit": "minutes",
                "confidence": 0.8,
                "source": "measured",
            },
            "car_minutes_each_way": {
                "value": 30,
                "unit": "minutes",
                "confidence": 0.8,
                "source": "measured",
            },
            "monthly_car_cost": {
                "value": 500,
                "unit": "USD/month",
                "confidence": 0.8,
                "source": "quoted",
            },
            "current_transport_monthly_cost": {
                "value": 100,
                "unit": "USD/month",
                "confidence": 0.8,
                "source": "measured",
            },
            "monthly_after_tax_income": {
                "value": 5000,
                "unit": "USD/month",
                "confidence": 0.8,
                "source": "measured",
            },
            "emergency_fund_months_after": {
                "value": 8,
                "unit": "months",
                "confidence": 0.8,
                "source": "measured",
            },
            "value_of_time": {
                "value": 50,
                "unit": "USD/hour",
                "confidence": 0.8,
                "source": "estimated",
            },
            "expected_need_stability_months": {
                "value": 24,
                "unit": "months",
                "confidence": 0.8,
                "source": "estimated",
            },
        },
    }


class CarDecisionTests(unittest.TestCase):
    def test_hard_constraint_fail_is_do_not_recommend(self):
        ir = base_ir()
        ir["variables"]["emergency_fund_months_after"]["value"] = 2

        result = evaluate_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "do_not_recommend")
        self.assertEqual(result["proof_state"]["goals"][0]["status"], "failed")
        self.assertEqual(result["proof_state"]["goals"][0]["severity"], "hard")

    def test_missing_income_is_insufficient_evidence(self):
        ir = base_ir()
        del ir["variables"]["monthly_after_tax_income"]

        result = evaluate_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "insufficient_evidence")
        income_goal = next(
            goal
            for goal in result["proof_state"]["goals"]
            if goal["claim"] == "income_affordability"
        )
        self.assertEqual(income_goal["status"], "open")

    def test_net_positive_strong_evidence_is_recommend(self):
        ir = base_ir()

        result = evaluate_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "recommend")

    def test_net_positive_weak_evidence_is_lean_yes(self):
        ir = base_ir()
        ir["variables"]["value_of_time"]["confidence"] = 0.4
        ir["variables"]["value_of_time"]["source"] = "guessed"

        result = evaluate_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "lean_yes")

    def test_unknown_value_of_time_opens_goal_instead_of_zeroing(self):
        ir = base_ir()
        ir["variables"]["value_of_time"]["value"] = None
        ir["variables"]["value_of_time"]["status"] = "unknown"
        ir["variables"]["value_of_time"]["source"] = "unknown"

        result = evaluate_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "insufficient_evidence")
        self.assertIsNone(result["derived_values"]["monthly_time_value"])
        benefit_goal = next(
            goal
            for goal in result["proof_state"]["goals"]
            if goal["claim"] == "benefit_exceeds_incremental_cost"
        )
        self.assertEqual(benefit_goal["status"], "open")
        self.assertIn("value_of_time", benefit_goal["dependencies"])

    def test_unknown_commute_input_opens_goal_without_crashing(self):
        ir = base_ir()
        ir["variables"]["commute_days_per_month"]["value"] = None
        ir["variables"]["commute_days_per_month"]["status"] = "unknown"
        ir["variables"]["commute_days_per_month"]["source"] = "unknown"

        result = evaluate_mod.evaluate(ir)

        self.assertIsNone(result["derived_values"]["monthly_commute_time_saved_hours"])
        self.assertIsNone(result["derived_values"]["net_monthly_value"])
        self.assertEqual(result["recommendation"]["status"], "insufficient_evidence")
        benefit_goal = next(
            goal
            for goal in result["proof_state"]["goals"]
            if goal["claim"] == "benefit_exceeds_incremental_cost"
        )
        self.assertEqual(benefit_goal["status"], "open")
        self.assertIn("commute_days_per_month", benefit_goal["dependencies"])

    def test_hard_constraint_beats_open_unknowns(self):
        ir = base_ir()
        ir["variables"]["emergency_fund_months_after"]["value"] = 2
        ir["variables"]["value_of_time"]["value"] = None
        ir["variables"]["value_of_time"]["status"] = "unknown"
        ir["variables"]["value_of_time"]["source"] = "unknown"

        result = evaluate_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "do_not_recommend")

    def test_warning_affordability_caps_positive_at_lean_no(self):
        ir = base_ir()
        # 900 / 5000 = 18%: above the 15% comfort line, below the 20% hard ceiling.
        ir["variables"]["monthly_car_cost"]["value"] = 900

        result = evaluate_mod.evaluate(ir)

        affordability = next(
            g
            for g in result["proof_state"]["goals"]
            if g["claim"] == "income_affordability"
        )
        self.assertEqual(affordability["status"], "failed")
        self.assertEqual(affordability["severity"], "warning")
        self.assertEqual(result["recommendation"]["status"], "lean_no")

    def test_evaluate_discloses_applied_default_assumptions(self):
        ir = base_ir()

        result = evaluate_mod.evaluate(ir)

        used = result["assumptions_used"]
        self.assertEqual(used["max_car_cost_income_ratio"], 0.15)
        self.assertIn("decision_margin", used)
        self.assertIn("comfort_value_monthly", used)
        # Variables the IR provides explicitly must not be listed as defaults.
        self.assertNotIn("monthly_car_cost", used)
        self.assertNotIn("commute_days_per_month", used)

    def test_hard_threshold_rounding(self):
        ir = base_ir()
        ir["variables"]["monthly_car_cost"]["value"] = 1000
        ir["variables"]["monthly_after_tax_income"]["value"] = 5000
        ir["variables"]["value_of_time"]["value"] = 100

        result = evaluate_mod.evaluate(ir)

        self.assertNotEqual(result["recommendation"]["status"], "do_not_recommend")
        affordability = next(
            goal
            for goal in result["proof_state"]["goals"]
            if goal["claim"] == "income_affordability"
        )
        self.assertEqual(affordability["status"], "failed")
        self.assertEqual(affordability["severity"], "warning")
        self.assertIn("20.0%", affordability["reason"])

    def test_validator_accepts_unknown_null_with_status(self):
        ir = base_ir()
        ir["variables"]["value_of_time"]["value"] = None
        ir["variables"]["value_of_time"]["status"] = "unknown"
        ir["variables"]["value_of_time"]["source"] = "unknown"

        self.assertEqual(validate_ir(ir), [])

    def test_validator_rejects_null_without_unknown_status(self):
        ir = base_ir()
        ir["variables"]["value_of_time"]["value"] = None

        errors = validate_ir(ir)

        self.assertTrue(any("status must be 'unknown'" in error for error in errors))

    def test_validator_uses_domain_model_required_variables(self):
        ir = base_ir()
        del ir["variables"]["monthly_after_tax_income"]

        errors = validate_ir(ir)

        self.assertTrue(
            any(
                "missing required variables for domain 'car'" in error
                for error in errors
            )
        )
        self.assertTrue(any("monthly_after_tax_income" in error for error in errors))

    def test_lean_generator_refuses_unknown_numeric_inputs(self):
        ir = base_ir()
        ir["variables"]["value_of_time"]["value"] = None
        ir["variables"]["value_of_time"]["status"] = "unknown"
        ir["variables"]["value_of_time"]["source"] = "unknown"

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(ir, handle)
            path = handle.name

        proc = subprocess.run(
            ["python3", "-m", verifier_mod.__name__, path],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("value_of_time", proc.stdout)


if __name__ == "__main__":
    unittest.main()
