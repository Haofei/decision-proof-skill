#!/usr/bin/env python3
"""Validate a Decision IR JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.validation import load_json, validate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Decision IR JSON file.")
    parser.add_argument("ir_json", type=Path)
    args = parser.parse_args()

    try:
        ir = load_json(args.ir_json)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
        return 1

    errors = validate(ir)
    print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
