"""Rent-vs-buy domain.

The methodology — variables, constraints (cash-safety threshold, affordability
band, the decisive stay-vs-break-even comparison), recommendation mapping, and
sensitivity — is declared in ``manifest.json`` and executed by the shared
``model_engine``. There is no hand-written methodology math here.

The only code is two **vetted finance primitives** that genuinely cannot be
expressed as formula data (a closed-form amortization payment and a stateful
month-by-month break-even simulation). They are written and reviewed once and
referenced by name from the manifest; an author never writes them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_proof.core import model_engine
from decision_proof.core.domain_metadata import domain_manifest
from decision_proof.core.guidance import manifest_guidance
from decision_proof.core.next_questions import manifest_next_questions
from decision_proof.core.verifier import (
    goal_hard_failed,
    hard_failed_any,
    has_open_goal,
    load_ir,
    non_negative_or_none,
    run_checks,
)

MANIFEST = domain_manifest(Path(__file__).with_name("manifest.json"))

MAX_HORIZON_YEARS = 40


# --- vetted finance primitives ---------------------------------------------


def mortgage_payment(params: dict[str, float | None]) -> float | None:
    """Standard fixed-rate monthly payment (principal + interest)."""
    loan = params.get("loan")
    annual_rate = params.get("annual_rate")
    term_years = params.get("term_years")
    if loan is None or annual_rate is None or term_years is None:
        return None
    n = int(round(term_years * 12))
    monthly_rate = annual_rate / 12
    if loan <= 0 or n <= 0:
        return 0.0
    if monthly_rate <= 0:
        return loan / n
    growth = (1 + monthly_rate) ** n
    return loan * monthly_rate * growth / (growth - 1)


def rent_buy_break_even(params: dict[str, float | None]) -> float | None:
    """First year (>=1) at which buying's net worth catches renting's.

    Apples-to-apples: both paths start with the same upfront cash (down payment
    + closing) and the same monthly housing budget. The buyer pays the mortgage,
    tax, maintenance and HOA; the renter pays rent and invests the monthly
    difference plus the retained upfront capital. None if buying never overtakes
    renting within the horizon.
    """
    if any(value is None for value in params.values()):
        return None
    price = params["price"]
    balance = params["loan"]
    payment = params["payment"]
    renter_assets = params["upfront_cash"]
    rent = params["rent0"]
    monthly_rate = params["annual_rate"] / 12
    tax_rate = params["tax_rate"]
    maint_rate = params["maint_rate"]
    hoa = params["hoa"]
    selling_pct = params["selling_pct"]

    invest_m = (1 + params["invest"]) ** (1 / 12) - 1
    apprec_m = (1 + params["apprec"]) ** (1 / 12) - 1
    rent_growth_m = (1 + params["rent_growth"]) ** (1 / 12) - 1
    home_value = float(price)
    max_months = int(round(min(params["term_years"], MAX_HORIZON_YEARS) * 12))

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


model_engine.register_primitive("mortgage_payment", mortgage_payment)
model_engine.register_primitive("rent_buy_break_even", rent_buy_break_even)


# --- domain hooks (delegations) --------------------------------------------


def evaluate(ir: dict[str, Any]) -> dict[str, Any]:
    return model_engine.evaluate(ir, MANIFEST)


def thresholds(ir: dict[str, Any]) -> dict[str, Any]:
    return model_engine.thresholds(ir, MANIFEST)


def verify(ir_path: Path) -> dict[str, Any]:
    """Deterministic domain invariants (no Lean backend yet)."""
    ir = load_ir(ir_path)
    evaluation = evaluate(ir)
    sensitivity = thresholds(ir)

    status = evaluation["recommendation"]["status"]
    goals = evaluation["proof_state"]["goals"]
    derived = evaluation["derived_values"]
    flip = sensitivity["flip_conditions"]
    used = evaluation.get("assumptions_used", {})
    positive = status in {"recommend", "lean_yes"}
    variables = ir.get("variables", {})

    break_even = derived.get("break_even_years")
    max_home_price = flip.get("max_home_price_within_budget")

    break_even_priors = MANIFEST.get("derived_value_assumptions", {}).get(
        "break_even_years", []
    )
    break_even_disclosed = break_even is None or all(
        prior in variables or prior in used for prior in break_even_priors
    )

    checks = [
        (
            "cash_safety_hard_fail_blocks_positive",
            not (goal_hard_failed(goals, "cash_safety") and positive),
            "a hard cash-safety failure cannot coexist with recommend/lean_yes",
        ),
        (
            "affordability_hard_fail_blocks_positive",
            not (goal_hard_failed(goals, "affordability") and positive),
            "a hard affordability failure cannot coexist with recommend/lean_yes",
        ),
        (
            "do_not_recommend_requires_hard_fail",
            status != "do_not_recommend" or hard_failed_any(goals),
            "do_not_recommend must be backed by a hard-severity failed goal",
        ),
        (
            "insufficient_evidence_requires_open_goal",
            status != "insufficient_evidence" or has_open_goal(goals),
            "insufficient_evidence requires at least one open proof goal",
        ),
        (
            "break_even_years_non_negative",
            non_negative_or_none(break_even),
            "break_even_years must be non-negative or null",
        ),
        (
            "max_home_price_within_budget_non_negative",
            non_negative_or_none(max_home_price),
            "max_home_price_within_budget must be non-negative or null",
        ),
        (
            "numeric_break_even_discloses_priors",
            break_even_disclosed,
            "every modeling prior behind a numeric break-even must be explicit in variables or disclosed in assumptions_used",
        ),
    ]
    return run_checks(
        checks,
        predicate="RentVsBuyDeterministicInvariants",
        recommendation_status=status,
    )


def guidance(run: dict[str, Any]) -> dict[str, str]:
    return manifest_guidance(run, MANIFEST)


def next_questions(ir: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    return manifest_next_questions(ir, run, MANIFEST)
