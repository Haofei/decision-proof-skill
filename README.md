# Decision Proof

**Decision Proof helps you decide whether to buy or rent a home by showing the buy/rent break-even horizon, the safety constraints, and the exact assumptions that would flip the recommendation.**

Rent-vs-buy is the flagship; the same engine also handles a graduate-school decision and a small car-buying demo. It is an auditable decision tool, not an oracle: it shows that the recommendation follows from the stated assumptions — **it does not prove the assumptions are true.**

Most people reason through high-stakes choices by feel: buy or rent, go to graduate school, take the job, move cities, wait, invest, quit. The feeling is often meaningful, but it is hard to inspect. Decision Proof translates that feeling into variables, thresholds, constraints, proof goals, and conclusion-flipping conditions — and checks that the conclusion is consistent with them.

The core question changes from:

```text
What should I do?
```

to:

```text
Under what conditions does this choice become reasonable?
What would have to change for the conclusion to flip?
```

## What It Does

- Interviews the user for goals, options, constraints, evidence, and assumptions.
- Builds a structured Decision IR.
- Checks hard constraints before soft preferences.
- Computes break-even thresholds and sensitivity points.
- Tracks proof goals as `closed`, `open`, `failed`, or `assumption`.
- Uses Python for calculations and deterministic verifiers for proof-checked rule closure.
- Produces conditional recommendations instead of pretending to know the future.

## Decision Workspace Shape

The product direction is a Decision Workspace rather than a plain chat surface:

- Decision summary
- Variables / evidence table
- Proof goals
- Sensitivity and flip conditions
- Decision reports
- Decision diffs between runs

See `references/product-architecture.md` for the longer-term domain-pack, API, and data-model shape.

## Current MVP

The repository now routes evaluation through a small domain runtime:

```text
decision_proof/core/domain_runtime.py
  resolves decision.type via decision_proof/domains/*/manifest.json

decision_proof/runtime.py
  is the public Python runtime surface for evaluation, thresholds, guidance, verification, and next questions
```

The first implemented domain is personal car decisions. It now has two evaluator levels:

```text
evaluate_car_decision.py:
  buy_car vs no_car

evaluate_car_options.py:
  no_car / used_gas_car / used_ev / new_car / wait_6_months style comparison
```

The option-based evaluator is still intentionally small, but it supports the Scenario Comparison shape: each option has its own cost, time, risk, evidence quality, proof goals, status, main risk, and ranking.

The primary repository demo is now the option-comparison path rather than the binary buy/no-buy path:

```text
1. no_car
2. used_gas_car
3. used_ev
4. new_car
5. wait_6_months
```

That path shows the product shape better because the runtime can rank alternatives, surface hard constraints per option, name the main unresolved risk, and propose the next few conclusion-changing questions.

The same pattern is now implemented as a second domain for a graduate-school decision:

```text
Should I go to graduate school or work directly?
```

A third domain models rent vs buy, the canonical high-stakes housing decision:

```text
Should I buy this home or keep renting?
```

It computes the buy/rent break-even horizon (how many years you must stay for buying to beat renting) and checks it against two hard constraints — post-purchase cash safety and housing affordability — before the horizon comparison decides the recommendation. The car domain is kept only as a small feature demo.

That example shows why the approach is useful. Many people compare only:

```text
direct work salary < post-grad salary
```

Decision Proof reframes it as:

```text
How much do I fall behind first?
How many years does it take to break even?
What salary makes the decision low-risk friendly?
```

## Installation

Clone this repository, then copy it into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R decision-proof-skill ~/.codex/skills/decision-proof
```

Start a new Codex thread and invoke:

```text
Use $decision-proof to help me decide whether I should buy a car.
```

## Scripts

Preferred CLI surface. The flagship flow is the rent-vs-buy decision; car is a small feature demo:

```bash
python3 -m decision_proof.cli demo rent-vs-buy
python3 -m decision_proof.cli evaluate examples/rent-vs-buy-decision.json
python3 -m decision_proof.cli report examples/rent-vs-buy-decision.json --md-out /tmp/rent_vs_buy.md
python3 -m decision_proof.cli next-questions examples/rent-vs-buy-decision.json
python3 -m decision_proof.cli verify examples/rent-vs-buy-decision.json
```

Car remains available as a feature demo:

```bash
python3 -m decision_proof.cli demo car-options
python3 -m decision_proof.cli report examples/car-options-comparison.json --json-out /tmp/options_run.json --md-out /tmp/options_report.md
```

Validate a Decision IR JSON file:

```bash
python3 -m decision_proof.cli validate examples/car-decision.json
python3 -m decision_proof.cli validate examples/graduate-school-decision.json
```

Evaluate any supported decision through the domain runtime:

```bash
python3 -m decision_proof.cli evaluate examples/car-decision.json
python3 -m decision_proof.cli evaluate examples/graduate-school-decision.json
python3 -m decision_proof.cli evaluate examples/car-options-comparison.json
```

Generate a Decision Report:

```bash
python3 -m decision_proof.cli report examples/car-decision.json --json-out /tmp/run_unknown.json --md-out /tmp/report.md
python3 -m decision_proof.cli report examples/graduate-school-decision.json --json-out /tmp/grad_run.json --md-out /tmp/grad_report.md
```

Compare two decision runs:

```bash
python3 -m decision_proof.cli report examples/car-decision-value-time-100.json --json-out /tmp/run_value_time_100.json
python3 -m decision_proof.cli diff /tmp/run_unknown.json /tmp/run_value_time_100.json --md
```

Validate a domain pack and run its golden cases:

```bash
python3 -m decision_proof.cli domain-validate decision_proof/domains/rent_vs_buy
python3 -m decision_proof.cli domain-test decision_proof/domains/rent_vs_buy
```

Run tests:

```bash
python3 -m unittest discover -s tests
```

## Domain Packs

Supported domain packs currently live under:

```text
decision_proof/domains/
  car/
    manifest.json
    questions.md
    domain.py
  graduate_school/
    manifest.json
    questions.md
    domain.py
  rent_vs_buy/
    manifest.json
    questions.md
    domain.py
```

`manifest.json` now drives runtime routing metadata and domain-level validation for the shared runtime and `decision_proof.cli validate`.

## Design Boundary

The deterministic verifiers (a per-domain invariant checker plus the cross-domain
global verifier) check **rule closure**:

- a hard-failed constraint can never coexist with a positive recommendation
- `insufficient_evidence` requires at least one open proof goal
- numeric outputs declare their inputs, and unknowns never silently feed them
- every defaulted prior behind a numeric output is disclosed
- option rankings respect status order

They do **not** check:

- whether user estimates are true
- whether future stability claims are true
- whether the user's comfort value is psychologically accurate
- whether external salaries, prices, or laws are current

That boundary is intentional. The verifiers prove rule closure, not reality.

## Why This Helps

A good decision tool should not erase intuition. It should make intuition inspectable.

Decision Proof helps turn:

```text
I feel like this is worth it.
```

into:

```text
This becomes worth it if:
- my time is worth at least $62.50/hour, or
- I get at least 5 hours/month back, or
- I accept this as a $250/month lifestyle upgrade.
```

That is often the moment a decision becomes clear.
