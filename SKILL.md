---
name: decision-proof
description: Build conditional, auditable decision models from real-world choices. Use when the user wants help deciding whether to buy, move, quit, choose, invest, compare options, or understand what would change a conclusion, especially when the decision involves goals, tradeoffs, constraints, assumptions, evidence, sensitivity analysis, proof states, or Decision IR. The skill interviews the user, converts the decision into structured premises and rules, checks constraints and calculations, identifies open proof goals, and outputs conditional recommendations rather than absolute advice.
---

# Decision Proof

## Overview

Use this skill to turn an ambiguous real-world decision into a conditional proof model. Do not directly decide for the user. Show what follows from the stated premises, what remains unproven, and what variable changes would flip the conclusion.

Supported domains now route through `decision_proof/core/domain_runtime.py`, which resolves `decision.type` using `decision_proof/domains/*/manifest.json`.

- `personal_finance_mobility` -> `decision_proof/domains/car/` (demo domain)
- `graduate_school` / `education_career` -> `decision_proof/domains/graduate_school/`
- `rent_vs_buy` / `housing` -> `decision_proof/domains/rent_vs_buy/`

For car questions, read `references/car-decision-model.md`. For graduate-school questions, use the break-even framing from `examples/graduate-school-notes.md` and `examples/graduate-school-decision.json`. For rent-vs-buy questions, use `examples/rent-vs-buy-decision.json` and `decision_proof/domains/rent_vs_buy/questions.md`; the core output is the buy/rent break-even horizon checked against cash-safety and affordability constraints.

## Core Rule

Treat every recommendation as conditional:

```text
If these premises, constraints, values, and estimates hold, then this conclusion follows.
If any critical premise changes, recompute the conclusion.
```

Never present a low-evidence estimate as a fact. Never ask Lean, a verifier, or a calculator to prove real-world truth. Use verification only to check that the conclusion follows from the provided premises and rules.

## Workflow

1. Restate the decision target and candidate options.
2. Identify the user's objective, hard constraints, soft preferences, key variables, evidence, and assumptions.
3. Ask at most 3-5 high-leverage questions when required information is missing. Prefer the questions most likely to change the conclusion.
4. Build or update Decision IR. Read `references/decision-ir-schema.md` when emitting or editing full IR.
5. Check hard constraints before soft utility. If a hard constraint fails, do not use soft benefits to override it unless the user explicitly changes the constraint.
6. Evaluate calculations and proof state. Read `references/proof-state.md` for goal states.
7. Output a conditional recommendation using the fixed output contract in `references/output-format.md`.
8. Include conclusion-flipping conditions and next most valuable evidence.

## Modes

- **Quick mode**: Ask at most 3 questions, then give a rough conditional conclusion with key assumptions and largest risks.
- **Strict mode**: Build Decision IR, evaluate constraints, list proof goals, show calculations, and run scripts when possible.
- **Comparison mode**: Model multiple options and compare them through the same constraints and utility dimensions.
- **Recompute mode**: Update only the changed variables, rerun evaluation, and show a decision diff.
- **Counterfactual mode**: Answer "what would make the conclusion change?" with thresholds and failed/open goals.

## Recommendation States

Use only these states:

- `recommend`: hard constraints pass, evidence is reasonably strong, and the conclusion is robust.
- `lean_yes`: likely favorable, but depends on important assumptions or weak evidence.
- `insufficient_evidence`: key variables or constraints are unknown.
- `lean_no`: likely unfavorable, but a few variables could change the outcome.
- `do_not_recommend`: a hard constraint fails or the main derivation fails.

## Resources

- `references/decision-ir-schema.md`: Decision IR fields and conventions.
- `references/proof-state.md`: Lean-like proof goals and goal status semantics.
- `references/car-decision-model.md`: MVP car decision variables, rules, and thresholds.
- `references/output-format.md`: Required user-facing answer structure.
- `references/lean-backend.md`: Boundary and pipeline for generated Lean proof certificates.
- `references/decision-workspace.md`: Productized workspace/report/diff model for Decision Proof.
- `references/product-architecture.md`: Domain pack, run artifact, API, and data-model direction for productization.
- `python3 -m decision_proof.cli validate <ir.json>`: Validate a Decision IR JSON file.
- `python3 -m decision_proof.cli evaluate <ir.json>`: Evaluate any supported Decision IR JSON file through the runtime.
- `python3 -m decision_proof.cli report <ir.json> --json-out <run.json> --md-out <report.md>`: Generate a Markdown report and run artifact from a Decision IR.
- `python3 -m decision_proof.cli diff <from-run.json> <to-run.json> --md`: Compare two run artifacts and show decision diffs.
- `python3 -m decision_proof.cli next-questions <ir.json>`: Generate deterministic next questions.
- `python3 -m decision_proof.cli verify <ir.json>`: Run domain and global verifiers for a Decision IR.
- `python3 -m decision_proof.domains.car.verifier <ir.json> --out <proof.lean>`: Generate a concrete Lean proof certificate for a car-decision IR and call `lean` to check it.
