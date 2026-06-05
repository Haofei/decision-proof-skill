#!/usr/bin/env python3
"""Generate a Decision Proof report and run artifact from a Decision IR JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_proof.report import DomainRuntimeError, error_payload, load_json, make_run, render_markdown  # noqa: E402,F401


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Decision Proof report.")
    parser.add_argument("ir_json", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args()

    try:
        ir = load_json(args.ir_json)
        run = make_run(ir, args.ir_json, args.run_id)
        markdown = render_markdown(run)

        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(run, indent=2), encoding="utf-8")
        if args.md_out:
            args.md_out.parent.mkdir(parents=True, exist_ok=True)
            args.md_out.write_text(markdown, encoding="utf-8")
        if not args.json_out and not args.md_out:
            print(markdown)
        return 0
    except (DomainRuntimeError, ValueError) as exc:
        print(json.dumps(error_payload(exc), indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
