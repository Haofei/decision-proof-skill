# Lean Backend

Use Lean only for deterministic proof checking after the real-world estimates have been converted into concrete numbers.

## Boundary

Lean checks:

- cash safety predicates
- affordability predicates
- positive or non-positive net value
- the recommendation predicate implied by those facts

Lean does not check:

- whether user estimates are true
- whether future stability claims are true
- whether the user's comfort value is psychologically accurate
- whether external prices or laws are current

## Pipeline

```text
Decision IR JSON
  -> Python computes derived values
  -> generate_lean_car_proof.py emits a concrete .lean file
  -> lean checks theorem
  -> script returns proof_checked=true or an error
```

## Recommendation Predicates

The first Lean slice proves one of these:

- `LeanYes d`: cash safe, affordable, and net value positive.
- `LeanNo d`: cash safe, affordable, and net value not positive.
- `DoNotRecommend d`: cash safety fails or affordability hard ceiling fails.

This is intentionally narrow. It proves rule closure, not real-world truth.

## Near-Term Invariants

Prefer proving these invariants before adding more domain formulas:

- hard constraint failed implies `do_not_recommend`
- missing required variable implies `insufficient_evidence`
- unknown variables cannot be used as numeric zero unless explicitly defaulted
- recommendation status must match proof goals
- every derived value must cite dependencies
