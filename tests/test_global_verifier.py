from __future__ import annotations

import copy
import unittest
from pathlib import Path

from decision_proof.core import global_verifier as global_verifier_mod
from decision_proof.report import load_json, make_run

ROOT = Path(__file__).resolve().parents[1]


class GlobalVerifierTests(unittest.TestCase):
    def test_generated_run_passes_global_invariants(self):
        ir_path = ROOT / "examples" / "graduate-school-decision.json"
        run = make_run(load_json(ir_path), ir_path, "global_ok")

        self.assertTrue(run["global_verifier_result"]["ok"])
        self.assertTrue(run["derived_value_dependencies"])

    def test_hard_fail_cannot_become_positive_recommendation(self):
        ir_path = ROOT / "examples" / "car-decision.json"
        ir = load_json(ir_path)
        ir["variables"]["emergency_fund_balance"]["value"] = 2000
        ir["variables"]["value_of_time"]["value"] = 100
        run = make_run(ir, ir_path, "global_hard_fail")
        tampered = copy.deepcopy(run)
        tampered["recommendation"]["status"] = "recommend"

        result = global_verifier_mod.verify_run(
            tampered, expected_hash=tampered["input_ir_hash"]
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                item["id"] == "hard_fail_blocks_positive_recommendation"
                for item in result["failed_invariants"]
            )
        )

    def test_unknown_variable_cannot_feed_numeric_output(self):
        ir_path = ROOT / "examples" / "car-decision.json"
        run = make_run(load_json(ir_path), ir_path, "global_unknown")
        tampered = copy.deepcopy(run)
        tampered["derived_values"]["monthly_time_value"] = 0

        result = global_verifier_mod.verify_run(
            tampered, expected_hash=tampered["input_ir_hash"]
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                item["id"] == "unknown_variables_do_not_feed_numeric_outputs"
                for item in result["failed_invariants"]
            )
        )

    def test_option_ranking_cannot_put_bad_option_first(self):
        ir_path = ROOT / "examples" / "car-options-comparison.json"
        run = make_run(load_json(ir_path), ir_path, "global_option_rank")
        tampered = copy.deepcopy(run)
        tampered["comparison"]["ranking"] = ["new_car"] + [
            item for item in tampered["comparison"]["ranking"] if item != "new_car"
        ]

        result = global_verifier_mod.verify_run(
            tampered, expected_hash=tampered["input_ir_hash"]
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                item["id"] == "option_ranking_respects_status_order"
                for item in result["failed_invariants"]
            )
        )


if __name__ == "__main__":
    unittest.main()
