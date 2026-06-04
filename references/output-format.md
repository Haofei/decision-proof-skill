# Output Format

Use this structure for every substantive decision answer.

## 1. Current Conclusion

State the recommendation status and strength:

```text
Current conclusion: lean_no.
Under the current premises, buying the car is not supported by the pure money/time model. It becomes reasonable only if you are willing to pay about $185/month for comfort and optionality.
```

## 2. Key Derivation

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

## 3. Hard Constraint Status

Use check-style text:

```text
Hard constraints:
- Pass: emergency fund remains 8 months, above 6-month safety line.
- Pass: car cost is 9.4% of after-tax income, below 15% pressure threshold.
- Unknown: future need stability over 24 months.
```

## 4. Open Goals

List unclosed proof goals:

```text
Open goals:
- Vehicle monthly cost is still an estimate.
- Rideshare/current transport comparison is incomplete.
- Future work/location stability is assumed.
```

## 5. Sensitive Variables

List variables most likely to flip the conclusion:

```text
Sensitive variables:
- monthly_car_cost
- monthly_time_saved_hours
- value_of_time
- future commute/location stability
```

## 6. Next Most Valuable Evidence

Ask for the smallest useful evidence set:

```text
Next most valuable evidence:
- Real insurance quote.
- Parking cost.
- One week of actual commute times.
```

## Tone

Be explicit but not theatrical. The user wants a decision instrument, not a motivational speech.
