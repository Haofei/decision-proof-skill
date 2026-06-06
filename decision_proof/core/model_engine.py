"""Declarative model engine (Tier 1).

Interprets a manifest's ``priors`` / ``model`` / ``constraints`` /
``recommendation`` / ``sensitivity`` sections so a domain can express its
methodology as data instead of Python. A domain whose math fits the closed
primitive set needs no hand-written evaluator: its ``evaluate``/``thresholds``
are one-line delegations to this engine.

The engine never executes domain-supplied code; it only resolves a closed set of
vetted primitives and constraint kinds. That is what makes a manifest safe to
author by an LLM (or, in future, third parties).
"""

from __future__ import annotations

from typing import Any

from decision_proof.core.domain_shared import (
    boolish,
    evidence_quality_from_variables,
    goal,
    has_failed_goal,
    numeric_ir_value,
    raw_variable_value,
    recommendation_status,
    round_or_none,
    text_variable_value,
    threshold_goal,
)

# --- primitives -------------------------------------------------------------

# Vetted domain-specific primitives. Genuinely algorithmic compute (e.g. a
# stateful financial simulation) cannot be expressed as formula data without
# becoming a programming language; it is written and reviewed ONCE as code here
# and then referenced by name (with params) from any manifest. A primitive
# receives a dict of resolved param values and returns a number or None.
_PRIMITIVES: dict[str, Any] = {}


def register_primitive(name: str, fn: Any) -> None:
    _PRIMITIVES[name] = fn


def _product(operands: list[float]) -> float | None:
    result = 1.0
    for value in operands:
        if value is None:
            return None
        result *= value
    return result


def _sum(operands: list[float]) -> float | None:
    total = 0.0
    for value in operands:
        if value is None:
            return None
        total += value
    return total


def _difference(operands: list[float]) -> float | None:
    if any(value is None for value in operands):
        return None
    result = operands[0]
    for value in operands[1:]:
        result -= value
    return result


def _positive_difference(operands: list[float]) -> float | None:
    diff = _difference(operands)
    return None if diff is None else max(0.0, diff)


# --- value resolution -------------------------------------------------------


Resolver = Any  # Callable[[Any], float | None]


def _make_resolver(
    computed: dict[str, float | None],
    ir: dict[str, Any],
    priors: dict[str, float],
    used: dict[str, float],
) -> Resolver:
    """Resolve a reference to a number: literal, intermediate, variable, or prior.

    A prior resolved by default (absent or explicit-null in the IR) is recorded
    in ``used`` so it can be disclosed. The same resolver serves formulas and
    constraint operands, so a prior may be referenced directly as a limit.
    """

    def resolve(name: Any) -> float | None:
        if isinstance(name, (int, float)):
            return float(name)
        if name in computed:
            return computed[name]
        value = numeric_ir_value(ir, name)
        if value is not None:
            return value
        if name in priors:
            used[name] = float(priors[name])
            return float(priors[name])
        return None

    return resolve


def resolve_values(
    ir: dict[str, Any], manifest: dict[str, Any]
) -> tuple[dict[str, float | None], dict[str, float], Resolver]:
    """Compute every declared intermediate in declaration order.

    Returns (values, assumptions_used, resolver). Operands may reference
    variables, priors, literals, or earlier intermediates, so the manifest must
    list intermediates in dependency order.
    """
    priors = {
        str(key): float(value) for key, value in manifest.get("priors", {}).items()
    }
    computed: dict[str, float | None] = {}
    used: dict[str, float] = {}
    resolve = _make_resolver(computed, ir, priors, used)

    for name, spec in manifest.get("model", {}).get("intermediates", {}).items():
        computed[name] = _compute(spec, resolve, ir)
    return computed, used, resolve


def _compute(
    spec: dict[str, Any], resolve: Resolver, ir: dict[str, Any]
) -> float | None:
    primitive = spec.get("primitive")

    if primitive in {"product", "sum", "difference", "positive_difference"}:
        operands = [resolve(name) for name in spec.get("operands", [])]
        return {
            "product": _product,
            "sum": _sum,
            "difference": _difference,
            "positive_difference": _positive_difference,
        }[primitive](operands)

    if primitive == "ratio":
        numerator = resolve(spec.get("numerator"))
        denominator = resolve(spec.get("denominator"))
        if numerator is None or denominator is None:
            return None
        if spec.get("require_positive_denominator") and denominator <= 0:
            return None
        if denominator == 0:
            return None
        return numerator / denominator

    if primitive == "lookup":
        key = text_variable_value(ir, str(spec.get("key")))
        prior_name = spec.get("table", {}).get(key)
        if prior_name is None:
            return None
        return resolve(prior_name)

    if primitive in _PRIMITIVES:
        params = {
            str(name): resolve(ref) for name, ref in spec.get("params", {}).items()
        }
        return _PRIMITIVES[primitive](params)

    raise ValueError(f"unsupported model primitive: {primitive}")


# --- constraints ------------------------------------------------------------


def _render(template: Any, values: dict[str, float | None]) -> str:
    safe = {key: value for key, value in values.items() if value is not None}
    try:
        return str(template).format(**safe)
    except (KeyError, ValueError, IndexError):
        return str(template)


def _case_matches(
    condition: dict[str, Any] | None,
    ir: dict[str, Any],
    values: dict[str, float | None],
) -> bool:
    if not condition:
        return True
    if "all" in condition:
        return all(_case_matches(item, ir, values) for item in condition["all"])
    if "any" in condition:
        return any(_case_matches(item, ir, values) for item in condition["any"])
    if "value_unknown" in condition:
        return values.get(str(condition["value_unknown"])) is None
    if "value_lte" in condition:
        spec = condition["value_lte"]
        current = values.get(str(spec.get("name")))
        return current is not None and current <= float(spec.get("limit"))
    if "value_at_least" in condition:
        spec = condition["value_at_least"]
        current = values.get(str(spec.get("name")))
        limit = values.get(str(spec.get("limit")))
        return current is not None and limit is not None and current >= limit
    if "variable_unknown" in condition:
        return raw_variable_value(ir, str(condition["variable_unknown"])) is None
    if "bool_true" in condition:
        return boolish(raw_variable_value(ir, str(condition["bool_true"]))) is True
    if "text_equals" in condition:
        spec = condition["text_equals"]
        return text_variable_value(ir, str(spec.get("name"))) == str(spec.get("value"))
    return False


def build_goals(
    ir: dict[str, Any],
    manifest: dict[str, Any],
    values: dict[str, float | None],
    resolve: Resolver,
) -> list[dict[str, Any]]:
    goals = []
    for spec in manifest.get("constraints", []):
        kind = spec.get("kind")
        if kind == "threshold":
            goals.append(_threshold_constraint(spec, resolve))
        elif kind == "ratio_band":
            goals.append(_ratio_band_constraint(spec, resolve))
        elif kind == "cases":
            goals.append(_cases_constraint(spec, ir, values))
        else:
            raise ValueError(f"unsupported constraint kind: {kind}")
    return goals


def _ratio_band_constraint(spec: dict[str, Any], resolve: Resolver) -> dict[str, Any]:
    """Three-way band: <= comfort (closed/soft); <= hard (failed/warning);
    above (failed/hard)."""
    value = resolve(spec.get("value"))
    comfort = resolve(spec.get("comfort_limit"))
    hard = resolve(spec.get("hard_limit"))
    deps = spec.get("dependencies", [])

    def make(status: str, template: str, severity: str) -> dict[str, Any]:
        reason = _render(template, {"value": value, "comfort": comfort, "hard": hard})
        return goal(spec["id"], spec["claim"], status, reason, deps, severity=severity)

    if value is None or comfort is None or hard is None:
        return goal(
            spec["id"],
            spec["claim"],
            "open",
            spec.get("open_reason", ""),
            deps,
            severity="warning",
        )
    if value <= comfort:
        return make("closed", spec.get("reason_closed", ""), "soft")
    if value <= hard:
        return make("failed", spec.get("reason_comfort_breach", ""), "warning")
    return make("failed", spec.get("reason_hard_breach", ""), "hard")


def _threshold_constraint(spec: dict[str, Any], resolve: Resolver) -> dict[str, Any]:
    value = resolve(spec.get("value"))
    limit = resolve(spec.get("limit"))
    return threshold_goal(
        spec["id"],
        spec["claim"],
        value,
        spec.get("op", "gte"),
        limit,
        spec.get("dependencies", []),
        open_reason=spec.get("open_reason", ""),
        templates={
            "closed": spec.get("reason_closed", ""),
            "failed": spec.get("reason_failed", ""),
        },
        closed_severity=spec.get("severity_on_pass", "soft"),
        open_severity=spec.get("severity_on_open", "warning"),
        failed_severity=spec.get("severity_on_fail", "hard"),
    )


def _cases_constraint(
    spec: dict[str, Any],
    ir: dict[str, Any],
    values: dict[str, float | None],
) -> dict[str, Any]:
    for case in spec.get("cases", []):
        if _case_matches(case.get("when"), ir, values):
            return goal(
                spec["id"],
                spec["claim"],
                str(case.get("status")),
                _render(case.get("reason", ""), values),
                [str(dep) for dep in case.get("dependencies", [])],
                severity=case.get("severity"),
            )
    return goal(
        spec["id"],
        spec["claim"],
        "open",
        "no case matched",
        [],
        severity="warning",
    )


# --- assembly ---------------------------------------------------------------


def _mapped(mapping: dict[str, Any], resolve: Resolver) -> dict[str, float | None]:
    """Render an output->source map, supporting per-output rounding.

    A source is either a reference string (rounded to 2 dp) or
    ``{"source": ref, "round": n}``.
    """
    out: dict[str, float | None] = {}
    for output, spec in mapping.items():
        if isinstance(spec, dict):
            out[output] = round_or_none(
                resolve(spec.get("source")), spec.get("round", 2)
            )
        else:
            out[output] = round_or_none(resolve(spec))
    return out


def evaluate(ir: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    values, used, resolve = resolve_values(ir, manifest)
    goals = build_goals(ir, manifest, values, resolve)
    rec = manifest.get("recommendation", {})

    decisive = next(
        (c["claim"] for c in manifest.get("constraints", []) if c.get("decisive")),
        None,
    )
    goal_status = {item["claim"]: item["status"] for item in goals}
    positive_case = goal_status.get(decisive) == "closed"

    open_blocks = set(rec.get("open_blocks_conclusion", []))
    open_required = any(
        item["claim"] in open_blocks and item["status"] == "open" for item in goals
    )
    evidence = evidence_quality_from_variables(ir, rec.get("evidence_variables", []))
    status = recommendation_status(
        hard_failed=has_failed_goal(goals, severity="hard"),
        open_required=open_required,
        positive_case=positive_case,
        evidence_quality=evidence,
        caution_failed=has_failed_goal(goals, severity="warning"),
    )

    return {
        "assumptions_used": used,
        "derived_values": _mapped(manifest.get("derived_values", {}), resolve),
        "proof_state": {
            "target_claim": rec.get("target_claim", "decision"),
            "goals": goals,
        },
        "recommendation": {
            "status": status,
            "evidence_quality": evidence,
            "key_dependencies": rec.get("key_dependencies", []),
        },
    }


def thresholds(ir: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    _, _, resolve = resolve_values(ir, manifest)
    spec = manifest.get("sensitivity", {})

    current = _mapped(spec.get("current", {}), resolve)
    current["unknown_variables"] = sorted(
        name
        for name in spec.get("unknown_variables", [])
        if raw_variable_value(ir, name) is None
    )
    return {
        "current": current,
        "flip_conditions": _mapped(spec.get("flip_conditions", {}), resolve),
    }
