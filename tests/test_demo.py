from __future__ import annotations

import unittest

from decision_proof.demo import car_options_demo


class DemoTests(unittest.TestCase):
    def test_car_options_demo_summary(self):
        payload = car_options_demo()

        self.assertEqual(payload["best_option"], "used_gas_car")
        self.assertEqual(payload["ranking"][:3], ["used_gas_car", "used_ev", "no_car"])
        self.assertTrue(payload["next_questions"]["next_questions"][0]["id"].startswith("car.option.used_gas_car"))


if __name__ == "__main__":
    unittest.main()