# Output Format

Use this structure for every substantive decision answer.

The same structure is used by `python3 -m decision_proof.cli report`, which emits a Markdown report and a JSON run artifact. Use `python3 -m decision_proof.cli diff` to compare two run artifacts after a variable change.

## 1. Current Conclusion

State the recommendation status and strength, but make it executable rather than merely analytical:

```text
Current conclusion: lean_no.
Tilt against buying. On the current numbers, this is effectively a $185/month comfort and flexibility purchase.
```

## 2. Decision Guidance

Immediately tell the user what to focus on, what not to overthink, and what to do next:

```text
Focus on:
The decision currently turns on one unknown: whether your time is worth at least $62.5/hour.

Do not overthink:
Emergency-fund safety and affordability already pass; do not keep re-estimating them unless the numbers materially change.

Next step:
Decide what one regained hour is actually worth to you before tuning anything else.
```

## 3. Key Derivation

Show the decisive calculation in plain language:

```text
Monthly time saved:
20 days * 2 * (45 - 25) minutes / 60 = 13.3 hours/month

Monthly time value:
13.3 * $50 = $665/month

Incremental car cost:
$850 - $0 = $850/month

Net monthly value:
$665 - $850 = -$185/month
```

## 4. Hard Constraint Status

Use check-style text:

```text
Hard constraints:
- Pass: emergency fund remains 8 months, above 6-month safety line.
- Pass: car cost is 9.4% of after-tax income, below 15% pressure threshold.
- Unknown: future need stability over 24 months.
```

## 5. Open Goals

List unclosed proof goals:

```text
Open goals:
- Vehicle monthly cost is still an estimate.
- Rideshare/current transport comparison is incomplete.
- Future work/location stability is assumed.
```

## 6. Sensitive Variables

List the variables most likely to flip the conclusion, but prefer naming the dominant one and demoting the rest:

```text
Sensitive variables:
- monthly_car_cost
- monthly_time_saved_hours
- value_of_time
- future commute/location stability
```

## 7. Next Most Valuable Evidence

Ask for the smallest useful evidence set:

```text
Next most valuable evidence:
- Real insurance quote.
- Parking cost.
- One week of actual commute times.
```

## Tone

Be explicit but not theatrical. The user wants a decision instrument, not a motivational speech.
