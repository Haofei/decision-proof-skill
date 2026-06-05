"""Console entrypoint for Decision Proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from decision_proof.demo import car_options_demo
from decision_proof.core.domain_shared import error_payload
from decision_proof.diff import diff_runs, load_json as load_diff_json, render_markdown as render_diff_markdown
from decision_proof.next_questions import next_questions
from decision_proof.report import load_json as load_report_json, make_run, render_markdown
from decision_proof.runtime import DomainRuntimeError, evaluate
from decision_proof.validation import load_json as load_validation_json, validate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decision-proof", description="Decision Proof runtime and report CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a Decision IR file")
    validate_parser.add_argument("ir_json", type=Path)

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a Decision IR file")
    evaluate_parser.add_argument("ir_json", type=Path)

    report_parser = subparsers.add_parser("report", help="Generate a run artifact and Markdown report")
    report_parser.add_argument("ir_json", type=Path)
    report_parser.add_argument("--json-out", type=Path)
    report_parser.add_argument("--md-out", type=Path)
    report_parser.add_argument("--run-id", type=str)

    verify_parser = subparsers.add_parser("verify", help="Run domain and global verifiers for a Decision IR")
    verify_parser.add_argument("ir_json", type=Path)
    verify_parser.add_argument("--run-id", type=str)

    diff_parser = subparsers.add_parser("diff", help="Diff two run artifacts")
    diff_parser.add_argument("from_run_json", type=Path)
    diff_parser.add_argument("to_run_json", type=Path)
    diff_parser.add_argument("--md", action="store_true", help="Render Markdown instead of JSON")

    next_questions_parser = subparsers.add_parser("next-questions", help="Generate deterministic next questions")
    next_questions_parser.add_argument("ir_json", type=Path)

    demo_parser = subparsers.add_parser("demo", help="Run a repository demo flow")
    demo_parser.add_argument("name", choices=["car-options"])
    demo_parser.add_argument("--md-out", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        ir = load_validation_json(args.ir_json)
        errors = validate(ir)
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
        return 1 if errors else 0

    if args.command == "evaluate":
        try:
            print(json.dumps(evaluate(load_validation_json(args.ir_json)), indent=2))
            return 0
        except (DomainRuntimeError, ValueError) as exc:
            print(json.dumps(error_payload(exc), indent=2))
            return 1

    if args.command == "report":
        ir = load_report_json(args.ir_json)
        run = make_run(ir, args.ir_json, args.run_id)
        print(json.dumps(run, indent=2))
        if args.json_out:
            args.json_out.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
        if args.md_out:
            args.md_out.write_text(render_markdown(run) + "\n", encoding="utf-8")
        return 0

    if args.command == "verify":
        ir = load_report_json(args.ir_json)
        run = make_run(ir, args.ir_json, args.run_id)
        print(json.dumps({
            "global_verifier_result": run["global_verifier_result"],
            "verifier_result": run["verifier_result"],
        }, indent=2))
        return 0

    if args.command == "next-questions":
        ir = load_validation_json(args.ir_json)
        print(json.dumps(next_questions(ir), indent=2))
        return 0

    if args.command == "demo":
        if args.name != "car-options":
            raise ValueError(f"unsupported demo: {args.name}")
        payload = car_options_demo()
        if args.md_out:
            args.md_out.write_text(payload["markdown_report"] + "\n", encoding="utf-8")
        print(json.dumps({
            "demo": payload["demo"],
            "decision_id": payload["decision_id"],
            "best_option": payload["best_option"],
            "ranking": payload["ranking"],
            "options": payload["options"],
            "next_questions": payload["next_questions"],
        }, indent=2))
        return 0

    before = load_diff_json(args.from_run_json)
    after = load_diff_json(args.to_run_json)
    diff = diff_runs(before, after)
    if args.md:
        print(render_diff_markdown(diff))
    else:
        print(json.dumps(diff, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())