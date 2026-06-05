#!/usr/bin/env python3
"""Diff two Decision Proof run artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.diff import diff_runs, load_json, render_markdown  # noqa: E402,F401


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff two Decision Proof run artifacts.")
    parser.add_argument("from_run_json", type=Path)
    parser.add_argument("to_run_json", type=Path)
    parser.add_argument("--md", action="store_true", help="Render Markdown instead of JSON")
    args = parser.parse_args()

    diff = diff_runs(load_json(args.from_run_json), load_json(args.to_run_json))
    if args.md:
        print(render_markdown(diff))
    else:
        print(json.dumps(diff, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
