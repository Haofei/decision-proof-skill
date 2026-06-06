"""Console entrypoint for Decision Proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from decision_proof.core.domain_shared import error_payload
from decision_proof.demo import car_options_demo, rent_vs_buy_demo
from decision_proof.diff import diff_runs
from decision_proof.diff import load_json as load_diff_json
from decision_proof.diff import render_markdown as render_diff_markdown
from decision_proof.domain_tools import test_domain, validate_domain
from decision_proof.report import load_json as load_report_json
from decision_proof.report import make_run, render_markdown
from decision_proof.runtime import DomainRuntimeError, evaluate, next_questions
from decision_proof.validation import load_json as load_validation_json
from decision_proof.validation import validate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="decision-proof", description="Decision Proof runtime and report CLI."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a Decision IR file"
    )
    validate_parser.add_argument("ir_json", type=Path)

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Evaluate a Decision IR file"
    )
    evaluate_parser.add_argument("ir_json", type=Path)

    report_parser = subparsers.add_parser(
        "report", help="Generate a run artifact and Markdown report"
    )
    report_parser.add_argument("ir_json", type=Path)
    report_parser.add_argument("--json-out", type=Path)
    report_parser.add_argument("--md-out", type=Path)
    report_parser.add_argument("--run-id", type=str)

    verify_parser = subparsers.add_parser(
        "verify", help="Run domain and global verifiers for a Decision IR"
    )
    verify_parser.add_argument("ir_json", type=Path)
    verify_parser.add_argument("--run-id", type=str)

    diff_parser = subparsers.add_parser("diff", help="Diff two run artifacts")
    diff_parser.add_argument("from_run_json", type=Path)
    diff_parser.add_argument("to_run_json", type=Path)
    diff_parser.add_argument(
        "--md", action="store_true", help="Render Markdown instead of JSON"
    )

    next_questions_parser = subparsers.add_parser(
        "next-questions", help="Generate deterministic next questions"
    )
    next_questions_parser.add_argument("ir_json", type=Path)

    demo_parser = subparsers.add_parser("demo", help="Run a repository demo flow")
    demo_parser.add_argument("name", choices=["car-options", "rent-vs-buy"])
    demo_parser.add_argument("--md-out", type=Path)

    domain_validate_parser = subparsers.add_parser(
        "domain-validate", help="Validate a domain pack's manifest"
    )
    domain_validate_parser.add_argument("domain_dir", type=Path)
    domain_validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Release gate: treat contract warnings (e.g. too few golden cases) as errors",
    )

    domain_test_parser = subparsers.add_parser(
        "domain-test", help="Run a domain pack's golden cases"
    )
    domain_test_parser.add_argument("domain_dir", type=Path)

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
        print(
            json.dumps(
                {
                    "global_verifier_result": run["global_verifier_result"],
                    "verifier_result": run["verifier_result"],
                },
                indent=2,
            )
        )
        return 0

    if args.command == "next-questions":
        ir = load_validation_json(args.ir_json)
        print(json.dumps(next_questions(ir), indent=2))
        return 0

    if args.command == "demo":
        if args.name == "car-options":
            payload = car_options_demo()
            summary = {
                "demo": payload["demo"],
                "decision_id": payload["decision_id"],
                "best_option": payload["best_option"],
                "ranking": payload["ranking"],
                "options": payload["options"],
                "next_questions": payload["next_questions"],
            }
        elif args.name == "rent-vs-buy":
            payload = rent_vs_buy_demo()
            summary = {
                "demo": payload["demo"],
                "decision_id": payload["decision_id"],
                "recommendation": payload["recommendation"],
                "break_even_years": payload["break_even_years"],
                "guidance": payload["guidance"],
                "assumptions_used": payload["assumptions_used"],
                "next_questions": payload["next_questions"],
            }
        else:
            raise ValueError(f"unsupported demo: {args.name}")
        if args.md_out:
            args.md_out.write_text(payload["markdown_report"] + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "domain-validate":
        result = validate_domain(args.domain_dir, strict=args.strict)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    if args.command == "domain-test":
        result = test_domain(args.domain_dir)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

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
