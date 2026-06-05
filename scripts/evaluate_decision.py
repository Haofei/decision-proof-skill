#!/usr/bin/env python3
"""Evaluate a Decision IR file through the domain runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.domain_runtime import DomainRuntimeError, evaluate  # noqa: E402
from core.domain_shared import error_payload  # noqa: E402


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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