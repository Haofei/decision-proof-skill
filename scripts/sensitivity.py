#!/usr/bin/env python3
"""CLI wrapper for the car sensitivity module."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.domains.car.sensitivity import load_json, main, thresholds, var  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
