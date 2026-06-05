#!/usr/bin/env python3
"""CLI wrapper for the car Lean verifier."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.domains.car.verifier import cents, derive, emergency_months, lean_int, load_json, main, nat_floor, render_lean, var, verify_ir  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
