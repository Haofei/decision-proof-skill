#!/usr/bin/env python3
"""Evaluate a Decision IR file through the package runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.report import DomainRuntimeError, error_payload, load_json  # noqa: E402
from decision_proof.runtime import evaluate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a Decision IR JSON file.")
    parser.add_argument("ir_json", type=Path)
    args = parser.parse_args()

    try:
        print(json.dumps(evaluate(load_json(args.ir_json)), indent=2))
        return 0
    except (DomainRuntimeError, ValueError) as exc:
        print(json.dumps(error_payload(exc), indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())