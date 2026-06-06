from __future__ import annotations

import unittest
from pathlib import Path

from decision_proof.domain_tools import test_domain, validate_domain

ROOT = Path(__file__).resolve().parents[1]
RENT = ROOT / "decision_proof" / "domains" / "rent_vs_buy"


class DomainToolsTests(unittest.TestCase):
    def test_validate_domain_accepts_rent_vs_buy(self):
        result = validate_domain(RENT)

        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual(result["errors"], [])
        self.assertGreaterEqual(result["golden_cases"], 3)

    def test_golden_cases_reproduce(self):
        result = test_domain(RENT)

        self.assertTrue(result["ok"], result.get("cases"))
        self.assertEqual(result["count"], 3)
        for case in result["cases"]:
            self.assertEqual(case["failures"], [])

    def test_validate_domain_reports_missing_manifest(self):
        result = validate_domain(ROOT / "decision_proof" / "core")

        self.assertFalse(result["ok"])
        self.assertTrue(any("manifest.json" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
