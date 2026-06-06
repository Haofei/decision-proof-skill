from __future__ import annotations

import unittest
from pathlib import Path

from decision_proof.core import domain_runtime as runtime_mod
from decision_proof.report import load_json

ROOT = Path(__file__).resolve().parents[1]


class NextQuestionTests(unittest.TestCase):
    def test_car_next_questions_prioritize_value_of_time(self):
        ir = load_json(ROOT / "examples" / "car-decision.json")

        payload = runtime_mod.next_questions(ir)

        self.assertEqual(payload["next_questions"][0]["id"], "car.value_of_time")
        self.assertIn(
            "value_of_time", payload["next_questions"][0]["expected_variable_updates"]
        )
        self.assertIn(
            "insufficient_evidence",
            payload["next_questions"][0]["possible_conclusion_impact"],
        )

    def test_graduate_next_questions_focus_funding_and_salary(self):
        ir = load_json(ROOT / "examples" / "graduate-school-decision.json")

        payload = runtime_mod.next_questions(ir)
        question_ids = [item["id"] for item in payload["next_questions"]]

        self.assertIn("graduate_school.funding_path", question_ids)
        self.assertIn("graduate_school.post_grad_salary", question_ids)
        self.assertIn("post_grad_expected_salary", payload["expected_variable_updates"])

    def test_option_comparison_next_questions_follow_top_option(self):
        ir = load_json(ROOT / "examples" / "car-options-comparison.json")

        payload = runtime_mod.next_questions(ir)

        self.assertTrue(
            payload["next_questions"][0]["id"].startswith("car.option.used_gas_car")
        )
        self.assertIn(
            "reorder the shortlist",
            payload["next_questions"][0]["possible_conclusion_impact"],
        )


if __name__ == "__main__":
    unittest.main()
