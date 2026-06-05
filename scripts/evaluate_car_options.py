#!/usr/bin/env python3
"""CLI wrapper for the car option-comparison evaluator."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.domains.car.options import evaluate_option, evaluate_options, global_value, load_json, main, model_value, rank_key  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
