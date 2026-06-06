"""Rent-vs-buy domain evaluator.

Compares buying a home against renting an equivalent one over the user's
expected horizon. The core output is a break-even horizon (how many years you
must stay for buying to beat renting), checked against two hard constraints
(post-purchase cash safety and housing affordability) before the soft
horizon comparison decides the recommendation.

Market-rate assumptions (appreciation, rent growth, investment return, tax,
maintenance, closing/selling costs, term, down-payment fraction) are treated as
defaults/priors. The user-specific levers (home_price, mortgage_rate_annual,
monthly_rent, expected_years_in_home, monthly_after_tax_income,
emergency_fund_months_after) are explicit and, when missing, open a goal rather
than being silently defaulted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_proof.core.domain_metadata import domain_manifest
from decision_proof.core.domain_shared import (
    evidence_quality_from_variables,
    goal,
    has_failed_goal,
    numeric_ir_value,
    recommendation_status,
    threshold_goal,
)
from decision_proof.core.guidance import manifest_guidance
from decision_proof.core.next_questions import manifest_next_questions

MANIFEST = domain_manifest(Path(__file__).with_name("manifest.json"))

DEFAULTS = {
    "down_payment_pct": 0.20,
    "mortgage_term_years": 30.0,
    "home_appreciation_rate_annual": 0.03,
    "rent_growth_rate_annual": 0.03,
    "property_tax_rate_annual": 0.011,
    "maintenance_rate_annual": 0.01,
    "investment_return_rate_annual": 0.05,
    "closing_cost_pct": 0.03,
    "selling_cost_pct": 0.06,
    "hoa_monthly": 0.0,
    "min_emergency_fund_months": 6.0,
    "max_housing_cost_income_ratio": 0.28,
    "hard_max_housing_cost_income_ratio": 0.36,
}

MAX_HORIZON_YEARS = 40

AFFORDABILITY_DEPENDENCIES = [
    "home_price",
    "mortgage_rate_annual",
    "monthly_after_tax_income",
]
STAY_DEPENDENCIES = [
    "expected_years_in_home",
    "home_price",
    "mortgage_rate_annual",
    "monthly_rent",
]


def _monthly_payment(loan: float, monthly_rate: float, n_months: int) -> float:
    if loan <= 0 or n_months <= 0:
        return 0.0
    if monthly_rate <= 0:
        return loan / n_months
    growth = (1 + monthly_rate) ** n_months
    return loan * monthly_rate * growth / (growth - 1)


def _break_even_years(
    *,
    price: float,
    loan: float,
    monthly_rate: float,
    payment: float,
    down_payment: float,
    closing: float,
    rent0: float,
    tax_rate: float,
    maint_rate: float,
    hoa: float,
    apprec: float,
    rent_growth: float,
    invest: float,
    selling_pct: float,
    term_years: float,
) -> float | None:
    """First year (>=1) at which buying's net worth catches renting's.

    Apples-to-apples: both paths start with the same cash (down payment +
    closing) and the same monthly housing budget. The buyer pays the mortgage,
    property tax, maintenance and HOA; the renter pays rent and invests the
    monthly difference (positive or negative) plus the retained upfront capital.
    Returns None if buying never overtakes renting within the horizon.
    """
    invest_m = (1 + invest) ** (1 / 12) - 1
    apprec_m = (1 + apprec) ** (1 / 12) - 1
    rent_growth_m = (1 + rent_growth) ** (1 / 12) - 1

    balance = loan
    renter_assets = down_payment + closing
    home_value = float(price)
    rent = rent0
    max_months = int(round(min(term_years, MAX_HORIZON_YEARS) * 12))

    for month in range(1, max_months + 1):
        if balance > 0:
            interest = balance * monthly_rate
            principal = min(payment - interest, balance)
            balance -= principal
            mortgage_outlay = payment
        else:
            mortgage_outlay = 0.0
        buyer_outlay = (
            mortgage_outlay + price * tax_rate / 12 + price * maint_rate / 12 + hoa
        )
        renter_assets = renter_assets * (1 + invest_m) + (buyer_outlay - rent)
        home_value *= 1 + apprec_m
        rent *= 1 + rent_growth_m

        buyer_net = home_value * (1 - selling_pct) - max(balance, 0.0)
        if month >= 12 and buyer_net >= renter_assets:
            return month / 12
    return None


def _model(ir: dict[str, Any]) -> dict[str, Any]:
    price = numeric_ir_value(ir, "home_price")
    rate = numeric_ir_value(ir, "mortgage_rate_annual")
    rent0 = numeric_ir_value(ir, "monthly_rent")
    income = numeric_ir_value(ir, "monthly_after_tax_income")
    horizon = numeric_ir_value(ir, "expected_years_in_home")

    dp_pct = numeric_ir_value(ir, "down_payment_pct", DEFAULTS["down_payment_pct"])
    term = numeric_ir_value(ir, "mortgage_term_years", DEFAULTS["mortgage_term_years"])
    apprec = numeric_ir_value(
        ir, "home_appreciation_rate_annual", DEFAULTS["home_appreciation_rate_annual"]
    )
    rent_growth = numeric_ir_value(
        ir, "rent_growth_rate_annual", DEFAULTS["rent_growth_rate_annual"]
    )
    tax_rate = numeric_ir_value(
        ir, "property_tax_rate_annual", DEFAULTS["property_tax_rate_annual"]
    )
    maint_rate = numeric_ir_value(
        ir, "maintenance_rate_annual", DEFAULTS["maintenance_rate_annual"]
    )
    invest = numeric_ir_value(
        ir, "investment_return_rate_annual", DEFAULTS["investment_return_rate_annual"]
    )
    closing_pct = numeric_ir_value(ir, "closing_cost_pct", DEFAULTS["closing_cost_pct"])
    selling_pct = numeric_ir_value(ir, "selling_cost_pct", DEFAULTS["selling_cost_pct"])
    hoa = numeric_ir_value(ir, "hoa_monthly", DEFAULTS["hoa_monthly"])

    model: dict[str, Any] = {
        "price": price,
        "rate": rate,
        "rent0": rent0,
        "income": income,
        "horizon": horizon,
        "hoa": hoa,
        "down_payment_cash_needed": None,
        "monthly_mortgage_payment": None,
        "monthly_ownership_cost": None,
        "housing_cost_income_ratio": None,
        "break_even_years": None,
        "price_cost_coefficient": None,
    }

    if price is None:
        return model
    if rate is None:
        model["down_payment_cash_needed"] = price * dp_pct + price * closing_pct
        return model

    down_payment = price * dp_pct
    closing = price * closing_pct
    loan = price - down_payment
    monthly_rate = rate / 12
    n = int(round(term * 12))
    payment = _monthly_payment(loan, monthly_rate, n)
    monthly_ownership = payment + price * tax_rate / 12 + price * maint_rate / 12 + hoa

    model["down_payment_cash_needed"] = down_payment + closing
    model["monthly_mortgage_payment"] = payment
    model["monthly_ownership_cost"] = monthly_ownership
    if income:
        model["housing_cost_income_ratio"] = monthly_ownership / income

    amortization_factor = payment / loan if loan > 0 else 0.0
    model["price_cost_coefficient"] = (
        (1 - dp_pct) * amortization_factor + tax_rate / 12 + maint_rate / 12
    )

    if rent0 is not None:
        model["break_even_years"] = _break_even_years(
            price=price,
            loan=loan,
            monthly_rate=monthly_rate,
            payment=payment,
            down_payment=down_payment,
            closing=closing,
            rent0=rent0,
            tax_rate=tax_rate,
            maint_rate=maint_rate,
            hoa=hoa,
            apprec=apprec,
            rent_growth=rent_growth,
            invest=invest,
            selling_pct=selling_pct,
            term_years=term,
        )
    return model


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    model = _model(ir)
    emergency_fund = numeric_ir_value(ir, "emergency_fund_months_after")
    min_emergency = numeric_ir_value(
        ir, "min_emergency_fund_months", DEFAULTS["min_emergency_fund_months"]
    )
    max_ratio = numeric_ir_value(
        ir, "max_housing_cost_income_ratio", DEFAULTS["max_housing_cost_income_ratio"]
    )
    hard_max_ratio = numeric_ir_value(
        ir,
        "hard_max_housing_cost_income_ratio",
        DEFAULTS["hard_max_housing_cost_income_ratio"],
    )
    ratio = model["housing_cost_income_ratio"]
    break_even = model["break_even_years"]
    horizon = model["horizon"]

    goals = []
    goals.append(
        threshold_goal(
            "G1",
            "cash_safety",
            emergency_fund,
            "gte",
            min_emergency,
            ["emergency_fund_months_after", "min_emergency_fund_months"],
            open_reason="post-purchase emergency fund cannot be checked without emergency_fund_months_after",
            templates={
                "closed": lambda value, limit: (
                    f"{value:g} months of emergency fund remain, at or above the {limit:g}-month floor"
                ),
                "failed": lambda value, limit: (
                    f"only {value:g} months of emergency fund remain, below the {limit:g}-month floor"
                ),
            },
            failed_severity="hard",
        )
    )

    if ratio is None:
        goals.append(
            goal(
                "G2",
                "affordability",
                "open",
                "housing cost or income is unknown",
                AFFORDABILITY_DEPENDENCIES,
                severity="warning",
            )
        )
    elif ratio <= max_ratio:
        goals.append(
            goal(
                "G2",
                "affordability",
                "closed",
                f"housing cost is {ratio:.1%} of after-tax income",
                AFFORDABILITY_DEPENDENCIES,
                severity="soft",
            )
        )
    elif ratio <= hard_max_ratio:
        goals.append(
            goal(
                "G2",
                "affordability",
                "failed",
                f"housing cost is {ratio:.1%}, above the {max_ratio:.0%} comfort threshold",
                AFFORDABILITY_DEPENDENCIES,
                severity="warning",
            )
        )
    else:
        goals.append(
            goal(
                "G2",
                "affordability",
                "failed",
                f"housing cost is {ratio:.1%}, above the {hard_max_ratio:.0%} hard ceiling",
                AFFORDABILITY_DEPENDENCIES,
                severity="hard",
            )
        )

    inputs_ready = (
        horizon is not None
        and model["price"] is not None
        and model["rate"] is not None
        and model["rent0"] is not None
    )
    if not inputs_ready:
        goals.append(
            goal(
                "G3",
                "stay_long_enough",
                "open",
                "cannot compare your stay to the buy/rent break-even without expected_years_in_home, home_price, mortgage_rate_annual and monthly_rent",
                STAY_DEPENDENCIES,
                severity="warning",
            )
        )
    elif break_even is None:
        goals.append(
            goal(
                "G3",
                "stay_long_enough",
                "failed",
                f"buying does not break even versus renting within {MAX_HORIZON_YEARS} years on these assumptions",
                STAY_DEPENDENCIES,
                severity="warning",
            )
        )
    elif horizon >= break_even:
        goals.append(
            goal(
                "G3",
                "stay_long_enough",
                "closed",
                f"you plan to stay {horizon:g} years, at or beyond the {break_even:.1f}-year buy/rent break-even",
                STAY_DEPENDENCIES,
                severity="soft",
            )
        )
    else:
        goals.append(
            goal(
                "G3",
                "stay_long_enough",
                "failed",
                f"you plan to stay {horizon:g} years, short of the {break_even:.1f}-year buy/rent break-even",
                STAY_DEPENDENCIES,
                severity="warning",
            )
        )

    hard_failed = has_failed_goal(goals, severity="hard")
    open_required = any(
        item["id"] in {"G1", "G2", "G3"} and item["status"] == "open" for item in goals
    )
    positive_case = (
        horizon is not None and break_even is not None and horizon >= break_even
    )
    evidence = evidence_quality_from_variables(
        ir,
        [
            "home_price",
            "mortgage_rate_annual",
            "monthly_rent",
            "expected_years_in_home",
        ],
    )
    status = recommendation_status(
        hard_failed=hard_failed,
        open_required=open_required,
        positive_case=positive_case,
        evidence_quality=evidence,
    )

    return {
        "derived_values": {
            "down_payment_cash_needed": round(model["down_payment_cash_needed"], 2)
            if model["down_payment_cash_needed"] is not None
            else None,
            "monthly_mortgage_payment": round(model["monthly_mortgage_payment"], 2)
            if model["monthly_mortgage_payment"] is not None
            else None,
            "monthly_ownership_cost": round(model["monthly_ownership_cost"], 2)
            if model["monthly_ownership_cost"] is not None
            else None,
            "housing_cost_income_ratio": round(model["housing_cost_income_ratio"], 4)
            if model["housing_cost_income_ratio"] is not None
            else None,
            "break_even_years": round(break_even, 2)
            if break_even is not None
            else None,
        },
        "proof_state": {
            "target_claim": "buying_beats_renting_over_horizon",
            "goals": goals,
        },
        "recommendation": {
            "status": status,
            "evidence_quality": evidence,
            "key_dependencies": [
                "home_price",
                "mortgage_rate_annual",
                "monthly_rent",
                "expected_years_in_home",
                "monthly_after_tax_income",
            ],
        },
    }


def thresholds(ir: dict[str, Any]) -> dict[str, Any]:
    model = _model(ir)
    income = model["income"]
    hard_max_ratio = numeric_ir_value(
        ir,
        "hard_max_housing_cost_income_ratio",
        DEFAULTS["hard_max_housing_cost_income_ratio"],
    )
    break_even = model["break_even_years"]

    unknowns = [
        name
        for name in [
            "home_price",
            "mortgage_rate_annual",
            "monthly_rent",
            "expected_years_in_home",
            "monthly_after_tax_income",
        ]
        if numeric_ir_value(ir, name) is None
    ]

    max_home_price = None
    coefficient = model["price_cost_coefficient"]
    if coefficient and income:
        max_home_price = max(
            0.0, (hard_max_ratio * income - model["hoa"]) / coefficient
        )

    return {
        "current": {
            "break_even_years": round(break_even, 2)
            if break_even is not None
            else None,
            "expected_years_in_home": model["horizon"],
            "home_price": model["price"],
            "monthly_rent": model["rent0"],
            "monthly_ownership_cost": round(model["monthly_ownership_cost"], 2)
            if model["monthly_ownership_cost"] is not None
            else None,
            "housing_cost_income_ratio": round(model["housing_cost_income_ratio"], 4)
            if model["housing_cost_income_ratio"] is not None
            else None,
            "unknown_variables": sorted(set(unknowns)),
        },
        "flip_conditions": {
            "must_stay_years_to_break_even": round(break_even, 2)
            if break_even is not None
            else None,
            "max_home_price_within_budget": round(max_home_price, 2)
            if max_home_price is not None
            else None,
        },
    }


def verify(ir_path: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "proof_checked": False,
        "error": "no verifier implemented for rent_vs_buy",
        "returncode": 1,
    }


def guidance(run: dict[str, Any]) -> dict[str, str]:
    return manifest_guidance(run, MANIFEST)


def next_questions(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    return manifest_next_questions(ir, run, MANIFEST)
