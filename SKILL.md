---
name: decision-proof
description: Build conditional, auditable decision models from real-world choices. Use when the user wants help deciding whether to buy, move, quit, choose, invest, compare options, or understand what would change a conclusion, especially when the decision involves goals, tradeoffs, constraints, assumptions, evidence, sensitivity analysis, proof states, or Decision IR. The skill interviews the user, converts the decision into structured premises and rules, checks constraints and calculations, identifies open proof goals, and outputs conditional recommendations rather than absolute advice.
---

# Decision Proof

## Overview

Use this skill to turn an ambiguous real-world decision into a conditional proof model. Do not directly decide for the user. Show what follows from the stated premises, what remains unproven, and what variable changes would flip the conclusion.

The first MVP domain is personal car decisions. For car questions, read `references/car-decision-model.md` and use the scripts in `scripts/` with `python3 scripts/<name>.py ...` when a concrete IR or enough variables are available.

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
- `scripts/validate_ir.py`: Validate a Decision IR JSON file. Run as `python3 scripts/validate_ir.py <ir.json>`.
- `scripts/evaluate_car_decision.py`: Evaluate a car-decision IR and emit proof state. Run as `python3 scripts/evaluate_car_decision.py <ir.json>`.
- `scripts/sensitivity.py`: Estimate conclusion-flipping thresholds for car decisions. Run as `python3 scripts/sensitivity.py <ir.json>`.
- `scripts/generate_lean_car_proof.py`: Generate a concrete Lean proof certificate for a car-decision IR and call `lean` to check it. Run as `python3 scripts/generate_lean_car_proof.py <ir.json>`.
