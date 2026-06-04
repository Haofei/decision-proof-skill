# Decision IR Schema

Use Decision IR to persist the user's decision model outside the chat transcript. Prefer JSON when running scripts. YAML is acceptable for discussion, but convert to JSON before script execution unless a local parser is available.

## Minimal Shape

```json
{
  "decision": {
    "id": "buy_car_2026_06_04",
    "question": "Should I buy a car?",
    "type": "personal_finance_mobility",
    "stakes": "medium_high",
    "reversibility": "medium"
  },
  "options": [
    {"id": "buy_car", "label": "Buy a car"},
    {"id": "no_car", "label": "Do not buy a car"}
  ],
  "hard_constraints": [
    {
      "id": "cash_safety",
      "expression": "emergency_fund_months_after >= min_emergency_fund_months",
      "status": "unknown"
    }
  ],
  "variables": {
    "monthly_car_cost": {
      "value": 850,
      "unit": "USD/month",
      "confidence": 0.6,
      "source": "user_estimate"
    }
  },
  "rules": [],
  "proof_state": {
    "target_claim": "buy_car_better_than_no_car",
    "closed_goals": [],
    "open_goals": [],
    "failed_goals": []
  },
  "recommendation": {
    "status": "insufficient_evidence",
    "summary": "",
    "key_dependencies": []
  }
}
```

## Field Guidance

- `decision`: Store the stable identity, question, domain, stakes, and reversibility.
- `options`: Include all real alternatives, not only the option the user is tempted by.
- `hard_constraints`: Rules that must pass before recommendation. Do not trade them away as soft utility.
- `variables`: Store values with `unit`, `confidence`, and `source`.
- `rules`: Store deterministic formulas and dependencies.
- `derived_values`: Store computed outputs and their source dependencies.
- `proof_state`: Store target claim and goal statuses.
- `recommendation`: Store the current conditional recommendation.

## Evidence Sources

Use these source labels:

- `measured`: bank statement, actual travel logs, receipts, historical data.
- `quoted`: dealer quote, insurance quote, parking contract, official estimate.
- `estimated`: user's reasonable estimate.
- `guessed`: rough feeling with little support.
- `unknown`: missing or unclear.

Prefer split confidence dimensions in the final explanation:

- reasoning confidence
- evidence confidence
- model confidence
- stability confidence

Do not collapse these into a fake precise percentage unless the user asks for a scoring model.
