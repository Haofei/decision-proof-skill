# Car Decision Model

Use this reference for MVP questions such as:

- Should I buy a car?
- Should I buy new or used?
- Should I buy a car or keep using rideshare?
- Should I buy an EV or gas car?
- Should I buy now or wait?

## High-Leverage First Questions

Ask at most 3-5 questions before giving an initial model:

1. What is the main reason for the car: commute, family, freedom, social life, safety, or something else?
2. How many trips per month would change, and how much time does the current option take versus driving?
3. What is the estimated monthly car cost, including payment, insurance, parking, fuel or charging, maintenance, tax/registration, and depreciation?
4. After buying, how many months of emergency fund remain?
5. How likely are you to move, change jobs, or become remote in the next 12-24 months?

## Variables

Required for strict evaluation:

```yaml
usage:
  commute_days_per_month
  current_minutes_each_way
  car_minutes_each_way
  non_commute_trips_per_month
  average_non_commute_minutes_saved

cost:
  monthly_car_cost
  current_transport_monthly_cost

finance:
  monthly_after_tax_income
  emergency_fund_months_after
  emergency_fund_balance
  monthly_required_expenses
  min_emergency_fund_months
  max_car_cost_income_ratio
  hard_max_car_cost_income_ratio

preference:
  value_of_time
  comfort_value_monthly
  optionality_value_monthly
  decision_margin

uncertainty:
  expected_need_stability_months
```

## Defaults

Use these only as provisional defaults and label them as assumptions:

```yaml
min_emergency_fund_months: 6
max_car_cost_income_ratio: 0.15
hard_max_car_cost_income_ratio: 0.20
decision_margin: 0
comfort_value_monthly: 0
optionality_value_monthly: 0
expected_need_stability_months: null
```

## Derived Values

```text
monthly_commute_time_saved_hours =
  commute_days_per_month * 2 * (current_minutes_each_way - car_minutes_each_way) / 60

monthly_non_commute_time_saved_hours =
  non_commute_trips_per_month * average_non_commute_minutes_saved / 60

monthly_time_saved_hours =
  monthly_commute_time_saved_hours + monthly_non_commute_time_saved_hours

monthly_time_value =
  monthly_time_saved_hours * value_of_time

incremental_car_cost =
  monthly_car_cost - current_transport_monthly_cost

net_monthly_value =
  monthly_time_value + comfort_value_monthly + optionality_value_monthly - incremental_car_cost

car_cost_income_ratio =
  monthly_car_cost / monthly_after_tax_income

emergency_fund_months_after =
  emergency_fund_balance / monthly_required_expenses
```

## Recommendation Rules

- If `emergency_fund_months_after < min_emergency_fund_months`, use `do_not_recommend`.
- If `car_cost_income_ratio > hard_max_car_cost_income_ratio`, use `do_not_recommend`.
- If `car_cost_income_ratio > max_car_cost_income_ratio`, mark affordability as failed or high pressure.
- If hard constraints pass and `net_monthly_value > decision_margin`, use `lean_yes` or `recommend` depending on evidence strength and sensitivity.
- If hard constraints pass and `net_monthly_value` is near zero, use `insufficient_evidence`, `lean_no`, or "delay / cheaper car" depending on open goals.
- If hard constraints pass but `net_monthly_value < 0`, explain the required monthly comfort/optionality premium that would make the decision rational.

## Important Distinction

Do not say "buying the car is economically good" when only the combined lifestyle model supports it. Say:

```text
Pure financial/time-value model does not support buying.
The decision can still be reasonable if you are willing to pay $X/month for comfort, freedom, or reduced stress.
```
