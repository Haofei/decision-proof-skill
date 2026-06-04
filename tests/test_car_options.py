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


options_mod = load_module("evaluate_car_options", ROOT / "scripts" / "evaluate_car_options.py")


class CarOptionsTests(unittest.TestCase):
    def test_ranks_multiple_options(self):
        ir = options_mod.load_json(ROOT / "examples" / "car-options-comparison.json")

        result = options_mod.evaluate_options(ir)

        self.assertEqual(result["recommendation"]["best_option"], "used_gas_car")
        self.assertEqual(result["recommendation"]["status"], "lean_yes")
        self.assertEqual(result["ranking"][:3], ["used_gas_car", "used_ev", "no_car"])

    def test_new_car_hard_ceiling_fails(self):
        ir = options_mod.load_json(ROOT / "examples" / "car-options-comparison.json")

        result = options_mod.evaluate_options(ir)
        new_car = next(option for option in result["options"] if option["id"] == "new_car")

        self.assertEqual(new_car["status"], "do_not_recommend")
        self.assertIn("hard ceiling", new_car["main_risk"])

    def test_wait_option_keeps_unknowns_open(self):
        ir = options_mod.load_json(ROOT / "examples" / "car-options-comparison.json")

        result = options_mod.evaluate_options(ir)
        wait = next(option for option in result["options"] if option["id"] == "wait_6_months")
        open_claims = {
            goal["claim"]
            for goal in wait["proof_state"]["goals"]
            if goal["status"] == "open"
        }

        self.assertEqual(wait["status"], "insufficient_evidence")
        self.assertIn("income_affordability", open_claims)
        self.assertIn("utility_result", open_claims)


if __name__ == "__main__":
    unittest.main()
