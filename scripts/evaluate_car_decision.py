#!/usr/bin/env python3
"""CLI wrapper for the car single-decision evaluator."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.domains.car.evaluator import evaluate, emergency_fund_months, load_json, main, missing_for, value  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
