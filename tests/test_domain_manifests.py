from __future__ import annotations

import json
import unittest
from pathlib import Path

from decision_proof.core import domain_runtime as runtime_mod
from decision_proof.core import schema_validation as schema_mod
from decision_proof.report import load_json

ROOT = Path(__file__).resolve().parents[1]


class DomainManifestTests(unittest.TestCase):
    def test_car_manifest_matches_schema(self):
        manifest = json.loads(
            (ROOT / "decision_proof" / "domains" / "car" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )

        errors = schema_mod.validate_instance(manifest, "domain_manifest.schema.json")

        self.assertEqual(errors, [])

    def test_graduate_manifest_matches_schema(self):
        manifest = json.loads(
            (
                ROOT
                / "decision_proof"
                / "domains"
                / "graduate_school"
                / "manifest.json"
            ).read_text(encoding="utf-8")
        )

        errors = schema_mod.validate_instance(manifest, "domain_manifest.schema.json")

        self.assertEqual(errors, [])

    def test_runtime_prefers_manifest_metadata(self):
        car_ir = load_json(ROOT / "examples" / "car-decision.json")
        grad_ir = load_json(ROOT / "examples" / "graduate-school-decision.json")

        car_spec = runtime_mod.resolve_domain_spec(car_ir)
        grad_spec = runtime_mod.resolve_domain_spec(grad_ir)

        self.assertEqual(car_spec.model_path.name, "manifest.json")
        self.assertEqual(grad_spec.model_path.name, "manifest.json")


if __name__ == "__main__":
    unittest.main()
