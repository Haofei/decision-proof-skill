from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


runtime_mod = load_module("domain_runtime_manifest_tests", ROOT / "core" / "domain_runtime.py")
schema_mod = load_module("schema_validation_manifest_tests", ROOT / "core" / "schema_validation.py")
report_mod = load_module("generate_report_manifest_tests", ROOT / "scripts" / "generate_report.py")


class DomainManifestTests(unittest.TestCase):
    def test_car_manifest_matches_schema(self):
        manifest = json.loads((ROOT / "domains" / "car" / "manifest.json").read_text(encoding="utf-8"))

        errors = schema_mod.validate_instance(manifest, "domain_manifest.schema.json")

        self.assertEqual(errors, [])

    def test_graduate_manifest_matches_schema(self):
        manifest = json.loads((ROOT / "domains" / "graduate_school" / "manifest.json").read_text(encoding="utf-8"))

        errors = schema_mod.validate_instance(manifest, "domain_manifest.schema.json")

        self.assertEqual(errors, [])

    def test_runtime_prefers_manifest_metadata(self):
        car_ir = report_mod.load_json(ROOT / "examples" / "car-decision.json")
        grad_ir = report_mod.load_json(ROOT / "examples" / "graduate-school-decision.json")

        car_spec = runtime_mod.resolve_domain_spec(car_ir)
        grad_spec = runtime_mod.resolve_domain_spec(grad_ir)

        self.assertEqual(car_spec.model_path.name, "manifest.json")
        self.assertEqual(grad_spec.model_path.name, "manifest.json")


if __name__ == "__main__":
    unittest.main()