# Decision Proof Skill

Decision Proof is a Codex skill for turning messy real-world decisions into auditable, conditional decision models.

Most people reason through high-stakes choices by feel: buy the car, go to graduate school, take the job, move cities, wait, invest, quit. The feeling is often meaningful, but it is hard to inspect. This skill helps translate that feeling into variables, thresholds, constraints, proof goals, and conclusion-flipping conditions.

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
- Uses Python for calculations and a Lean backend for proof-checked rule closure.
- Produces conditional recommendations instead of pretending to know the future.

## Current MVP

The first implemented domain is personal car decisions:

```text
Should I buy a car?
Should I buy new or used?
Should I buy a car or keep using rideshare?
Should I buy an EV or gas car?
Should I buy now or wait?
```

The same pattern has also been tested manually on a graduate-school decision:

```text
Should I go to graduate school or work directly?
```

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

Validate a Decision IR JSON file:

```bash
python3 scripts/validate_ir.py examples/car-decision.json
```

Evaluate a car decision:

```bash
python3 scripts/evaluate_car_decision.py examples/car-decision.json
```

Compute sensitivity thresholds:

```bash
python3 scripts/sensitivity.py examples/car-decision.json
```

Generate and check a Lean proof:

```bash
python3 scripts/generate_lean_car_proof.py examples/car-decision.json --out /tmp/CarDecisionProof.lean
```

The Lean backend checks that the recommendation predicate follows from the concrete numbers and rules. It does not prove the real-world estimates are true.

## Design Boundary

Lean checks:

- hard constraint predicates
- affordability predicates
- positive or non-positive net value
- recommendation predicates implied by those facts

Lean does not check:

- whether user estimates are true
- whether future stability claims are true
- whether the user's comfort value is psychologically accurate
- whether external salaries, prices, or laws are current

That boundary is intentional. The skill proves rule closure, not reality.

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
