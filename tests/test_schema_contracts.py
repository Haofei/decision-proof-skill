from __future__ import annotations

import unittest
from pathlib import Path

from decision_proof.core import schema_validation as schema_mod
from decision_proof.report import load_json, make_run

ROOT = Path(__file__).resolve().parents[1]


class SchemaContractTests(unittest.TestCase):
    def test_example_ir_matches_decision_ir_schema(self):
        ir = load_json(ROOT / "examples" / "car-decision.json")

        errors = schema_mod.validate_instance(ir, "decision_ir.schema.json")

        self.assertEqual(errors, [])

    def test_generated_run_matches_run_artifact_schema(self):
        ir_path = ROOT / "examples" / "car-decision.json"
        run = make_run(load_json(ir_path), ir_path, "schema_run")

        errors = schema_mod.validate_instance(run, "run_artifact.schema.json")

        self.assertEqual(errors, [])

    def test_proof_goal_requires_severity(self):
        ir_path = ROOT / "examples" / "graduate-school-decision.json"
        run = make_run(load_json(ir_path), ir_path, "schema_grad")
        goal = dict(run["proof_state"]["goals"][0])
        del goal["severity"]

        errors = schema_mod.validate_instance(goal, "proof_goal.schema.json")

        self.assertTrue(
            any("'severity' is a required property" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
