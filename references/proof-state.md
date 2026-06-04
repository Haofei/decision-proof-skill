# Proof State

Proof state makes a messy decision feel like a Lean goal list. It does not prove real-world facts. It tracks whether the current premises are enough to support the target claim.

## Goal Statuses

- `closed`: The goal is satisfied under the current premises.
- `open`: More evidence is needed.
- `failed`: The goal is contradicted or below threshold.
- `assumption`: Temporarily assumed true, with weak or incomplete evidence.

## Typical Structure

```yaml
proof_state:
  target: "buy_car_better_than_no_car"
  goals:
    - id: "G1"
      claim: "financially_affordable"
      status: "closed"
      reason: "monthly_car_cost / monthly_after_tax_income is below threshold"
    - id: "G2"
      claim: "benefit_exceeds_incremental_cost"
      status: "failed"
      reason: "time value does not cover incremental monthly cost"
    - id: "G3"
      claim: "better_than_alternatives"
      status: "open"
      reason: "rideshare and rental costs are unknown"
```

## Reasoning Rules

- If any hard constraint fails, recommendation should normally be `do_not_recommend`.
- If hard constraints pass but a main economic or utility goal fails, prefer `lean_no` unless the user explicitly values non-monetary utility enough to cover the gap.
- If hard constraints pass and main goals are closed but key evidence is estimated or guessed, prefer `lean_yes`.
- If key variables are missing, use `insufficient_evidence`.
- If all major goals are closed with decent evidence and sensitivity is robust, use `recommend`.

## Open Goals

Always surface open goals in final output. Phrase them as useful next evidence:

- "Get an insurance quote."
- "Measure commute times for one week."
- "Compare monthly rideshare cost."
- "Confirm future location or work policy stability."
