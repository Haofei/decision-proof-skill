# Rent vs Buy — Interview Questions

High-value questions, roughly in the order they change the conclusion.

## Decision-defining

1. **How long do you realistically expect to keep this home?** (`expected_years_in_home`)
   The whole decision hinges on whether your stay clears the buy/rent break-even horizon.
2. **What is the home price you are considering?** (`home_price`)
3. **What mortgage rate can you actually lock today?** (`mortgage_rate_annual`)
4. **What does it cost to rent an equivalent home in the same area today?** (`monthly_rent`)

## Hard constraints

5. **What is your after-tax monthly income?** (`monthly_after_tax_income`)
   Used to judge whether the all-in monthly housing cost is a safe share of income.
6. **After the down payment and closing costs, how many months of expenses would your emergency fund still cover?** (`emergency_fund_months_after`)

## Assumptions (sensible defaults if unknown)

- `down_payment_pct` (default 20%)
- `mortgage_term_years` (default 30)
- `home_appreciation_rate_annual` (default 3%)
- `rent_growth_rate_annual` (default 3%)
- `property_tax_rate_annual` (default 1.1%)
- `maintenance_rate_annual` (default 1%)
- `investment_return_rate_annual` (default 5%, opportunity cost of the down payment)
- `closing_cost_pct` (default 3%)
- `selling_cost_pct` (default 6%)
- `hoa_monthly` (default 0)

These are market-rate priors. They are used as defaults but should be confirmed or overridden; they are never treated as user-verified facts.
