#!/usr/bin/env python3
"""Generate deterministic next questions for a partial Decision IR."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.next_questions import next_questions  # noqa: E402
from decision_proof.report import DomainRuntimeError, error_payload, load_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic next questions for a partial Decision IR.")
    parser.add_argument("ir_json", type=Path)
    args = parser.parse_args()

    try:
        print(json.dumps(next_questions(load_json(args.ir_json)), indent=2))
        return 0
    except (DomainRuntimeError, ValueError) as exc:
        print(json.dumps(error_payload(exc), indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())