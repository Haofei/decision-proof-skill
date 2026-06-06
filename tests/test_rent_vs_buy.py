from __future__ import annotations

import unittest
from pathlib import Path

from decision_proof import report as report_mod
from decision_proof.core import domain_runtime as runtime_mod

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "rent-vs-buy-decision.json"


def base_ir() -> dict:
    return report_mod.load_json(EXAMPLE)


def set_value(ir: dict, name: str, value) -> None:
    ir["variables"][name]["value"] = value


class RentVsBuyTests(unittest.TestCase):
    def test_runtime_detects_domain_and_short_stay_leans_rent(self):
        ir = base_ir()

        self.assertEqual(runtime_mod.domain_key(ir), "rent_vs_buy")

        result = runtime_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "lean_no")
        self.assertEqual(result["derived_values"]["break_even_years"], 10.75)
        stay = next(
            g
            for g in result["proof_state"]["goals"]
            if g["claim"] == "stay_long_enough"
        )
        self.assertEqual(stay["status"], "failed")
        self.assertEqual(stay["severity"], "warning")

    def test_report_passes_global_verifier_and_renders_clean_guidance(self):
        ir = base_ir()

        run = report_mod.make_run(ir, EXAMPLE, "rvb_test")
        markdown = report_mod.render_markdown(run)

        self.assertTrue(run["global_verifier_result"]["ok"])
        self.assertEqual(run["global_verifier_result"]["failed_invariants"], [])
        self.assertIn("Lean toward renting", run["guidance"]["summary"])
        self.assertIn("## Decision Guidance", markdown)
        self.assertNotIn("years years", markdown)

    def test_long_enough_stay_leans_buy(self):
        ir = base_ir()
        set_value(ir, "expected_years_in_home", 15)

        result = runtime_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "lean_yes")
        stay = next(
            g
            for g in result["proof_state"]["goals"]
            if g["claim"] == "stay_long_enough"
        )
        self.assertEqual(stay["status"], "closed")

    def test_unaffordable_income_is_hard_do_not_recommend(self):
        ir = base_ir()
        set_value(ir, "monthly_after_tax_income", 8000)

        result = runtime_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "do_not_recommend")
        affordability = next(
            g for g in result["proof_state"]["goals"] if g["claim"] == "affordability"
        )
        self.assertEqual(affordability["status"], "failed")
        self.assertEqual(affordability["severity"], "hard")

    def test_thin_emergency_fund_blocks_purchase(self):
        ir = base_ir()
        set_value(ir, "emergency_fund_months_after", 2)

        result = runtime_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "do_not_recommend")

    def test_unknown_horizon_is_insufficient_evidence(self):
        ir = base_ir()
        ir["variables"]["expected_years_in_home"]["value"] = None
        ir["variables"]["expected_years_in_home"]["status"] = "unknown"
        ir["variables"]["expected_years_in_home"]["source"] = "unknown"

        result = runtime_mod.evaluate(ir)

        self.assertEqual(result["recommendation"]["status"], "insufficient_evidence")
        stay = next(
            g
            for g in result["proof_state"]["goals"]
            if g["claim"] == "stay_long_enough"
        )
        self.assertEqual(stay["status"], "open")

    def test_next_questions_prioritizes_length_of_stay(self):
        ir = base_ir()
        run = report_mod.make_run(ir, EXAMPLE, "rvb_nq")

        questions = runtime_mod.next_questions(ir, run)["next_questions"]

        self.assertEqual(questions[0]["id"], "rent_vs_buy.length_of_stay")


if __name__ == "__main__":
    unittest.main()
