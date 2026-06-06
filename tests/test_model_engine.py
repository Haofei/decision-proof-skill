from __future__ import annotations

import unittest

from decision_proof.core import model_engine

# A whole domain expressed as data: no Python math. This is the Tier-1 promise
# that an expert's methodology can be authored declaratively.
MANIFEST = {
    "priors": {"target_ratio": 0.30},
    "model": {
        "intermediates": {
            "cost_ratio": {
                "primitive": "ratio",
                "numerator": "monthly_cost",
                "denominator": "monthly_income",
            }
        }
    },
    "constraints": [
        {
            "id": "G1",
            "claim": "affordable",
            "kind": "threshold",
            "value": "cost_ratio",
            "op": "lte",
            "limit": "target_ratio",
            "decisive": True,
            "severity_on_fail": "hard",
            "dependencies": ["monthly_cost", "monthly_income"],
            "open_reason": "need cost and income",
            "reason_closed": "cost is {value:.0%} of income",
            "reason_failed": "cost is {value:.0%}, above {limit:.0%}",
        }
    ],
    "recommendation": {
        "target_claim": "affordable",
        "evidence_variables": ["monthly_cost", "monthly_income"],
        "open_blocks_conclusion": ["affordable"],
    },
    "derived_values": {"cost_ratio": "cost_ratio"},
    "sensitivity": {
        "current": {"cost_ratio": "cost_ratio"},
        "flip_conditions": {},
        "unknown_variables": ["monthly_cost", "monthly_income"],
    },
}


def ir(cost, income) -> dict:
    def var(value):
        return {"value": value, "unit": None, "confidence": 0.9, "source": "stated"}

    variables = {}
    if cost is not None:
        variables["monthly_cost"] = var(cost)
    if income is not None:
        variables["monthly_income"] = var(income)
    return {"variables": variables}


class ModelEngineTests(unittest.TestCase):
    def test_primitives(self):
        self.assertEqual(model_engine._product([2.0, 3.0]), 6.0)
        self.assertIsNone(model_engine._product([2.0, None]))
        self.assertEqual(model_engine._difference([5.0, 2.0]), 3.0)
        self.assertEqual(model_engine._positive_difference([2.0, 5.0]), 0.0)

    def test_declarative_domain_passes_constraint(self):
        result = model_engine.evaluate(ir(1500, 6000), MANIFEST)

        self.assertEqual(result["derived_values"]["cost_ratio"], 0.25)
        goal = result["proof_state"]["goals"][0]
        self.assertEqual(goal["status"], "closed")
        self.assertEqual(result["recommendation"]["status"], "recommend")

    def test_declarative_domain_hard_fails(self):
        result = model_engine.evaluate(ir(2400, 6000), MANIFEST)

        goal = result["proof_state"]["goals"][0]
        self.assertEqual(goal["status"], "failed")
        self.assertEqual(goal["severity"], "hard")
        self.assertEqual(result["recommendation"]["status"], "do_not_recommend")
        self.assertIn("above 30%", goal["reason"])

    def test_missing_input_opens_goal_not_zero(self):
        result = model_engine.evaluate(ir(None, 6000), MANIFEST)

        goal = result["proof_state"]["goals"][0]
        self.assertEqual(goal["status"], "open")
        self.assertEqual(result["recommendation"]["status"], "insufficient_evidence")
        self.assertIsNone(result["derived_values"]["cost_ratio"])

    def test_prior_default_is_disclosed(self):
        result = model_engine.evaluate(ir(1500, 6000), MANIFEST)
        # target_ratio came from the prior default -> disclosed.
        self.assertEqual(result["assumptions_used"], {"target_ratio": 0.30})


if __name__ == "__main__":
    unittest.main()
