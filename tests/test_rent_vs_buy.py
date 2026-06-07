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

    def test_report_discloses_applied_default_assumptions(self):
        ir = base_ir()

        run = report_mod.make_run(ir, EXAMPLE, "rvb_assume")
        markdown = report_mod.render_markdown(run)

        used = run["assumptions_used"]
        # Defaults the example omits must be disclosed...
        self.assertIn("mortgage_term_years", used)
        self.assertEqual(used["property_tax_rate_annual"], 0.011)
        # ...and priors the example provides explicitly must NOT be re-listed.
        self.assertNotIn("down_payment_pct", used)
        self.assertNotIn("home_appreciation_rate_annual", used)
        self.assertIn("## Default Assumptions (priors)", markdown)
        self.assertIn("`property_tax_rate_annual`: 0.011", markdown)

    def test_warning_affordability_caps_positive_at_lean_no(self):
        ir = base_ir()
        # Long stay (would be positive) but housing cost lands in the
        # warning band (above comfort 28%, below hard ceiling 36%).
        set_value(ir, "expected_years_in_home", 15)
        set_value(ir, "monthly_after_tax_income", 13000)

        result = runtime_mod.evaluate(ir)

        affordability = next(
            g for g in result["proof_state"]["goals"] if g["claim"] == "affordability"
        )
        self.assertEqual(affordability["status"], "failed")
        self.assertEqual(affordability["severity"], "warning")
        self.assertEqual(result["recommendation"]["status"], "lean_no")

    def test_domain_verifier_passes_on_example(self):
        from decision_proof.domains.rent_vs_buy import domain as domain_mod

        result = domain_mod.verify(EXAMPLE)

        self.assertTrue(result["proof_checked"])
        self.assertEqual(result["failed_checks"], [])
        self.assertIn("numeric_break_even_discloses_priors", result["passed_checks"])

    def test_explicit_priors_do_not_false_fail_disclosure(self):
        # All modeling priors provided explicitly -> assumptions_used is empty,
        # but the disclosure check must still pass (P1: no false fail).
        from decision_proof.domains.rent_vs_buy import domain as domain_mod

        ir = base_ir()
        explicit = {
            "mortgage_term_years": 30,
            "home_appreciation_rate_annual": 0.03,
            "rent_growth_rate_annual": 0.03,
            "investment_return_rate_annual": 0.05,
            "property_tax_rate_annual": 0.011,
            "maintenance_rate_annual": 0.01,
            "closing_cost_pct": 0.03,
            "selling_cost_pct": 0.06,
            "hoa_monthly": 0,
            "min_emergency_fund_months": 6,
            "max_housing_cost_income_ratio": 0.28,
            "hard_max_housing_cost_income_ratio": 0.36,
        }
        for name, value in explicit.items():
            ir["variables"][name] = {
                "value": value,
                "unit": None,
                "confidence": 0.9,
                "source": "stated",
            }

        result = domain_mod.evaluate(ir)
        self.assertEqual(result["assumptions_used"], {})

        run = report_mod.make_run(ir, EXAMPLE, "rvb_explicit")
        self.assertTrue(run["verifier_result"]["proof_checked"])
        self.assertIn(
            "numeric_break_even_discloses_priors",
            run["verifier_result"]["passed_checks"],
        )
        self.assertTrue(run["global_verifier_result"]["ok"])

    def test_null_optional_prior_falls_back_without_crashing(self):
        ir = base_ir()
        for name in (
            "mortgage_term_years",
            "home_appreciation_rate_annual",
            "investment_return_rate_annual",
        ):
            ir["variables"][name] = {
                "value": None,
                "unit": None,
                "status": "unknown",
                "confidence": 0.0,
                "source": "unknown",
            }

        result = runtime_mod.evaluate(ir)

        # Falls back to defaults (no TypeError) and discloses every nulled prior.
        self.assertIsInstance(result["derived_values"]["break_even_years"], float)
        used = result["assumptions_used"]
        self.assertIn("mortgage_term_years", used)
        self.assertIn("home_appreciation_rate_annual", used)
        self.assertIn("investment_return_rate_annual", used)

    def test_run_exposes_complete_assumption_graph(self):
        ir = base_ir()
        run = report_mod.make_run(ir, EXAMPLE, "rvb_graph")

        assumptions = run["derived_value_assumptions"]
        self.assertIn("down_payment_pct", assumptions["break_even_years"])
        self.assertIn("selling_cost_pct", assumptions["break_even_years"])
        self.assertTrue(run["global_verifier_result"]["ok"])
        self.assertIn(
            "numeric_outputs_disclose_assumptions",
            run["global_verifier_result"]["passed_invariants"],
        )

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

    # --- semantic (model-level) validation -------------------------------

    def test_valid_example_passes_semantic_validation(self):
        from decision_proof.validation import validate

        self.assertEqual(validate(base_ir()), [])

    def test_semantic_validation_catches_out_of_range_inputs(self):
        from decision_proof.validation import validate

        ir = base_ir()
        set_value(ir, "mortgage_rate_annual", 6.5)  # percent entered as a rate
        set_value(ir, "down_payment_pct", 20)  # percent entered as a fraction
        set_value(ir, "monthly_after_tax_income", 0)
        set_value(ir, "home_price", "$600000")  # string, not a number

        errors = validate(ir)
        joined = " | ".join(errors)
        self.assertIn("mortgage_rate_annual", joined)
        self.assertIn("down_payment_pct", joined)
        self.assertIn("monthly_after_tax_income", joined)
        self.assertIn("home_price", joined)

    # --- property-based monotonicity -------------------------------------

    def _derived(self, ir, key):
        return runtime_mod.evaluate(ir)["derived_values"][key]

    def test_higher_rate_raises_monthly_payment(self):
        low, high = base_ir(), base_ir()
        set_value(high, "mortgage_rate_annual", 0.085)
        self.assertGreater(
            self._derived(high, "monthly_mortgage_payment"),
            self._derived(low, "monthly_mortgage_payment"),
        )

    def test_higher_price_worsens_affordability(self):
        base, pricier = base_ir(), base_ir()
        set_value(pricier, "home_price", 750000)
        self.assertGreater(
            self._derived(pricier, "housing_cost_income_ratio"),
            self._derived(base, "housing_cost_income_ratio"),
        )

    def test_higher_rent_lowers_break_even(self):
        base, pricier_rent = base_ir(), base_ir()
        set_value(pricier_rent, "monthly_rent", 3600)
        self.assertLess(
            self._derived(pricier_rent, "break_even_years"),
            self._derived(base, "break_even_years"),
        )

    def test_longer_stay_never_weakens_the_buy_case(self):
        # positive_case is (horizon >= break_even); once true for some horizon
        # it must stay true for every longer horizon.
        positive = {"recommend", "lean_yes"}
        seen_positive = False
        for years in range(1, 21):
            ir = base_ir()
            set_value(ir, "expected_years_in_home", years)
            status = runtime_mod.evaluate(ir)["recommendation"]["status"]
            if status in positive:
                seen_positive = True
            elif seen_positive:
                self.fail(
                    f"buy case weakened at {years} years (status={status}) after being positive"
                )


if __name__ == "__main__":
    unittest.main()
