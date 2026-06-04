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


sensitivity_mod = load_module("sensitivity", ROOT / "scripts" / "sensitivity.py")


class SensitivityTests(unittest.TestCase):
    def test_unknown_non_commute_still_reports_commute_break_even(self):
        ir = {
            "variables": {
                "commute_days_per_month": {"value": 4},
                "current_minutes_each_way": {"value": 60},
                "car_minutes_each_way": {"value": 30},
                "non_commute_trips_per_month": {"value": 10},
                "average_non_commute_minutes_saved": {"value": None, "status": "unknown"},
                "monthly_car_cost": {"value": 300},
                "current_transport_monthly_cost": {"value": 50},
                "value_of_time": {"value": None, "status": "unknown"},
            }
        }

        result = sensitivity_mod.thresholds(ir)

        self.assertEqual(result["current"]["known_monthly_time_saved_hours"], 4.0)
        self.assertEqual(result["flip_conditions"]["break_even_value_of_time"], 62.5)
        self.assertIn("average_non_commute_minutes_saved", result["current"]["unknown_variables"])


if __name__ == "__main__":
    unittest.main()
