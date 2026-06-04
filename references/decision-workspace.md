# Decision Workspace

Decision Proof should behave like a decision compiler, not a generic advice chatbot.

## Product Loop

1. Capture the user's decision and candidate options.
2. Ask the smallest set of conclusion-changing questions.
3. Build or update Decision IR.
4. Evaluate constraints, derived values, sensitivity, and proof goals.
5. Verify deterministic rule closure when inputs are complete enough.
6. Emit a report and save a run artifact.
7. Recompute and diff when variables change.

## Workspace Panels

- **Decision Summary**: question, options, current status, verifier badge.
- **Variables / Evidence Table**: value, unit, source, confidence, status, used-in goals.
- **Proof Goals**: closed, open, failed, and assumption goals with reasons.
- **Sensitivity**: break-even thresholds and conclusion-flipping variables.
- **Decision Diff**: what changed between runs and why the conclusion moved.

## Verifier Badge

Show verification as a product state, not as the main user-facing concept:

```text
PASS: Rule closure checked
OPEN: Evidence incomplete
FAIL: Hard constraint failed
```

Clarify that checked means:

```text
The conclusion follows from the stated premises and rules.
```

It does not mean:

```text
The real-world estimates are guaranteed true.
```

## Next Product Step

The current car evaluator is buy/no-buy. The next major engine change is option-based evaluation:

```text
no_car
used_gas_car
used_ev
new_car
wait_6_months
```

Each option should carry its own cost, time, risk, constraints, utility, evidence quality, and proof goals.
