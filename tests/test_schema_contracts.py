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


report_mod = load_module("generate_report_schema_tests", ROOT / "scripts" / "generate_report.py")
schema_mod = load_module("schema_validation", ROOT / "core" / "schema_validation.py")


class SchemaContractTests(unittest.TestCase):
    def test_example_ir_matches_decision_ir_schema(self):
        ir = report_mod.load_json(ROOT / "examples" / "car-decision.json")

        errors = schema_mod.validate_instance(ir, "decision_ir.schema.json")

        self.assertEqual(errors, [])

    def test_generated_run_matches_run_artifact_schema(self):
        ir_path = ROOT / "examples" / "car-decision.json"
        run = report_mod.make_run(report_mod.load_json(ir_path), ir_path, "schema_run")

        errors = schema_mod.validate_instance(run, "run_artifact.schema.json")

        self.assertEqual(errors, [])

    def test_proof_goal_requires_severity(self):
        ir_path = ROOT / "examples" / "graduate-school-decision.json"
        run = report_mod.make_run(report_mod.load_json(ir_path), ir_path, "schema_grad")
        goal = dict(run["proof_state"]["goals"][0])
        del goal["severity"]

        errors = schema_mod.validate_instance(goal, "proof_goal.schema.json")

        self.assertTrue(any("'severity' is a required property" in error for error in errors))


if __name__ == "__main__":
    unittest.main()