"""Shared guidance helpers for decision reports."""

from __future__ import annotations

from typing import Any


def format_currency(value: Any, suffix: str = "") -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    amount = float(value)
    if abs(amount) >= 1000:
        rendered = f"${amount:,.0f}"
        return f"{rendered}{suffix}"
    rounded_int = round(amount)
    rounded_tenth = round(amount, 1)
    if abs(amount - rounded_int) < 1e-9:
        rendered = f"${amount:,.0f}"
    elif abs(amount - rounded_tenth) < 1e-9:
        rendered = f"${amount:,.1f}"
    else:
        rendered = f"${amount:,.2f}"
    return f"{rendered}{suffix}"


def goal_lookup(proof_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        goal.get("claim"): goal
        for goal in proof_state.get("goals", [])
        if goal.get("claim")
    }


def first_goal_with_status(
    proof_state: dict[str, Any],
    claims: set[str],
    status: str,
    *,
    severity: str | None = None,
) -> dict[str, Any] | None:
    for item in proof_state.get("goals", []):
        if item.get("claim") not in claims or item.get("status") != status:
            continue
        if severity is not None and item.get("severity") != severity:
            continue
        return item
    return None


def rank_flip_levers(
    candidates: list[dict[str, Any]], *, positive_case: bool
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        current_value = candidate.get("current_value")
        threshold_value = candidate.get("threshold_value")
        higher_is_better = bool(candidate.get("higher_is_better"))
        if not isinstance(current_value, (int, float)) or not isinstance(
            threshold_value, (int, float)
        ):
            continue
        if positive_case:
            delta = (
                (current_value - threshold_value)
                if higher_is_better
                else (threshold_value - current_value)
            )
        else:
            delta = (
                (threshold_value - current_value)
                if higher_is_better
                else (current_value - threshold_value)
            )
        if delta < 0:
            continue
        scale = max(abs(float(threshold_value)), 1.0)
        ranked.append({**candidate, "distance": delta / scale})
    return sorted(ranked, key=lambda item: item["distance"])


def describe_top_flip_lever(
    candidates: list[dict[str, Any]], *, positive_case: bool
) -> tuple[str | None, str | None]:
    ranked = rank_flip_levers(candidates, positive_case=positive_case)
    if not ranked:
        return (None, None)

    focus = ranked[0]
    if positive_case:
        relation = "above" if focus["higher_is_better"] else "below"
        sentence = (
            f"The conclusion is most sensitive to {focus['label']}. It stays favorable while it remains {relation} "
            f"{focus['threshold_text']}; you are currently at {focus['current_text']}."
        )
    else:
        relation = "up to" if focus["higher_is_better"] else "down to"
        sentence = (
            f"The closest way to flip this is {focus['label']}. It would need to move {relation} "
            f"{focus['threshold_text']}; you are currently at {focus['current_text']}."
        )
    return sentence, focus.get("next_step")


def metric_value(
    run: dict[str, Any],
    spec: dict[str, Any],
    goal_map: dict[str, dict[str, Any]] | None = None,
) -> Any:
    if not isinstance(spec, dict):
        return None
    source = str(spec.get("source") or "current")
    key = spec.get("key")
    if source == "current":
        return run.get("sensitivity", {}).get("current", {}).get(key)
    if source == "flip":
        return run.get("sensitivity", {}).get("flip_conditions", {}).get(key)
    if source == "derived":
        return run.get("derived_values", {}).get(key)
    if source == "recommendation":
        return run.get("recommendation", {}).get(key)
    if source == "goal" and goal_map is not None:
        goal = goal_map.get(str(spec.get("claim")), {})
        field = str(spec.get("field") or "reason")
        return goal.get(field)
    return None


def format_manifest_value(value: Any, spec: dict[str, Any]) -> str:
    fallback = str(spec.get("fallback") or "unknown")
    if value is None:
        return fallback

    fmt = str(spec.get("format") or "raw")
    suffix = str(spec.get("suffix") or "")
    if fmt == "currency":
        return format_currency(value, suffix)
    if fmt == "float1":
        if not isinstance(value, (int, float)):
            return fallback
        return f"{float(value):.1f}{suffix}"
    if fmt == "float2":
        if not isinstance(value, (int, float)):
            return fallback
        return f"{float(value):.2f}{suffix}"
    if fmt == "int":
        if not isinstance(value, (int, float)):
            return fallback
        return f"{int(round(float(value)))}{suffix}"
    return f"{value}{suffix}"


def render_manifest_template(
    template: str | None,
    placeholders: dict[str, dict[str, Any]],
    run: dict[str, Any],
    goal_map: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    if template is None:
        return None
    values = {
        name: format_manifest_value(metric_value(run, spec, goal_map), spec)
        for name, spec in placeholders.items()
        if isinstance(name, str) and isinstance(spec, dict)
    }
    return template.format(**values)


def placeholders_are_numeric(
    run: dict[str, Any],
    placeholders: dict[str, dict[str, Any]],
    goal_map: dict[str, dict[str, Any]] | None = None,
) -> bool:
    for spec in placeholders.values():
        if not isinstance(metric_value(run, spec, goal_map), (int, float)):
            return False
    return True


def manifest_lever_candidates(
    run: dict[str, Any], levers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for lever in levers:
        if not isinstance(lever, dict):
            continue
        current_spec = {
            "source": "current",
            "key": lever.get("current_key"),
            "format": lever.get("format"),
            "suffix": lever.get("suffix"),
            "fallback": "unknown",
        }
        threshold_spec = {
            "source": "flip",
            "key": lever.get("threshold_key"),
            "format": lever.get("format"),
            "suffix": lever.get("suffix"),
            "fallback": "unknown",
        }
        current_value = metric_value(run, current_spec)
        threshold_value = metric_value(run, threshold_spec)
        candidates.append(
            {
                "label": lever.get("label"),
                "current_value": current_value,
                "threshold_value": threshold_value,
                "higher_is_better": bool(lever.get("higher_is_better")),
                "current_text": format_manifest_value(current_value, current_spec),
                "threshold_text": format_manifest_value(
                    threshold_value, threshold_spec
                ),
                "next_step": lever.get("next_step"),
            }
        )
    return candidates


def manifest_passed_constraint_deprioritize(
    proof_state: dict[str, Any], labels: dict[str, str]
) -> str | None:
    goal_map = goal_lookup(proof_state)
    passed = [
        label
        for claim, label in labels.items()
        if goal_map.get(claim, {}).get("status") == "closed"
    ]
    if not passed:
        return None
    if len(passed) == 1:
        return f"{passed[0].capitalize()} already passes; do not keep re-estimating it unless the number materially changes."
    return f"{passed[0].capitalize()} and {passed[1]} already pass; do not keep re-estimating them unless the numbers materially change."


def _guidance_condition_matches(
    condition: dict[str, Any] | None, goal_map: dict[str, dict[str, Any]]
) -> bool:
    if not condition:
        return True
    if "any" in condition:
        return any(
            _guidance_condition_matches(item, goal_map)
            for item in condition["any"]
            if isinstance(item, dict)
        )
    if "all" in condition:
        return all(
            _guidance_condition_matches(item, goal_map)
            for item in condition["all"]
            if isinstance(item, dict)
        )
    if "goal_status" in condition:
        goal_status = condition["goal_status"]
        claim = str(goal_status.get("claim") or "")
        statuses = goal_status.get("statuses", [])
        if isinstance(statuses, str):
            statuses = [statuses]
        return goal_map.get(claim, {}).get("status") in {str(item) for item in statuses}
    return False


def _resolve_case_text(
    case: dict[str, Any],
    field: str,
    run: dict[str, Any],
    goal_map: dict[str, dict[str, Any]],
) -> str:
    goal_reason_claim = case.get(f"{field}_from_goal_reason")
    if isinstance(goal_reason_claim, str):
        return str(
            goal_map.get(goal_reason_claim, {}).get("reason") or case.get(field) or ""
        )

    numeric_variant = case.get(f"{field}_when_numeric")
    if isinstance(numeric_variant, dict):
        placeholders = numeric_variant.get("placeholders", {})
        if placeholders_are_numeric(run, placeholders, goal_map):
            rendered = render_manifest_template(
                numeric_variant.get("template"), placeholders, run, goal_map
            )
            if rendered is not None:
                return rendered

    template = case.get(f"{field}_template")
    placeholders = case.get(f"{field}_placeholders", {})
    if isinstance(template, str):
        rendered = render_manifest_template(template, placeholders, run, goal_map)
        if rendered is not None:
            return rendered

    return str(case.get(field) or "")


def _goal_case_guidance(run: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    goal_map = goal_lookup(run.get("proof_state", {}))
    for case in config.get("cases", []):
        if not isinstance(case, dict) or not _guidance_condition_matches(
            case.get("when"), goal_map
        ):
            continue
        return {
            "summary": str(case.get("summary") or ""),
            "focus": _resolve_case_text(case, "focus", run, goal_map),
            "deprioritize": str(case.get("deprioritize") or ""),
            "next_step": _resolve_case_text(case, "next_step", run, goal_map),
        }

    fallback = config.get("default", {})
    if isinstance(fallback, dict):
        return {
            "summary": str(
                fallback.get("summary") or "The current conclusion is conditional."
            ),
            "focus": str(
                fallback.get("focus")
                or "Follow the closest flip condition before broadening the analysis."
            ),
            "deprioritize": str(
                fallback.get("deprioritize")
                or "Do not spread effort evenly across every estimate."
            ),
            "next_step": str(
                fallback.get("next_step")
                or "Resolve the next conclusion-changing variable."
            ),
        }
    return default_guidance(run)


def _flip_lever_guidance(run: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    proof_state = run.get("proof_state", {})
    goal_map = goal_lookup(proof_state)
    status = run.get("recommendation", {}).get("status")
    positive_statuses = {
        str(item) for item in config.get("positive_statuses", ["lean_yes", "recommend"])
    }
    negative_statuses = {
        str(item)
        for item in config.get("negative_statuses", ["lean_no", "do_not_recommend"])
    }
    positive_case = status in positive_statuses
    deprioritize = manifest_passed_constraint_deprioritize(
        proof_state, config.get("passed_constraint_labels", {})
    )

    hard_fail_config = config.get("hard_fail", {})
    hard_fail = first_goal_with_status(
        proof_state,
        {str(item) for item in hard_fail_config.get("claims", [])},
        "failed",
        severity=str(hard_fail_config.get("severity"))
        if hard_fail_config.get("severity") is not None
        else None,
    )
    if hard_fail is not None:
        next_step = str(
            hard_fail_config.get("next_step_fallback")
            or "Revisit the decision only after the hard constraint is back inside the safe range."
        )
        override = hard_fail_config.get("claim_overrides", {}).get(
            hard_fail.get("claim"), {}
        )
        if isinstance(override, dict):
            threshold_spec = {
                "source": "flip",
                "key": override.get("threshold_key"),
                "format": override.get("format"),
                "suffix": override.get("suffix"),
                "fallback": "unknown",
            }
            threshold_value = metric_value(run, threshold_spec, goal_map)
            if isinstance(threshold_value, (int, float)) and isinstance(
                override.get("template"), str
            ):
                next_step = override["template"].format(
                    threshold=format_manifest_value(threshold_value, threshold_spec)
                )
        return {
            "summary": str(
                hard_fail_config.get("summary")
                or "Do not treat this as a soft-preference choice yet; a hard constraint is failing."
            ),
            "focus": str(hard_fail.get("reason") or "A hard constraint is failing."),
            "deprioritize": deprioritize
            or str(
                hard_fail_config.get("deprioritize_fallback")
                or "Do not spend more time on softer upside until the hard constraint is resolved."
            ),
            "next_step": next_step,
        }

    focus = None
    next_step = None
    unknown_focus = config.get("unknown_focus", {})
    if isinstance(unknown_focus, dict):
        current_spec = {"source": "current", "key": unknown_focus.get("current_key")}
        threshold_spec = {
            "source": "flip",
            "key": unknown_focus.get("threshold_key"),
            "format": unknown_focus.get("format"),
            "suffix": unknown_focus.get("suffix"),
            "fallback": "unknown",
        }
        current_value = metric_value(run, current_spec, goal_map)
        threshold_value = metric_value(run, threshold_spec, goal_map)
        if current_value is None and isinstance(threshold_value, (int, float)):
            threshold = format_manifest_value(threshold_value, threshold_spec)
            template = str(unknown_focus.get("focus_template") or "")
            focus = template.format(threshold=threshold) if template else None
            next_step = unknown_focus.get("next_step")

    if focus is None:
        focus, next_step = describe_top_flip_lever(
            manifest_lever_candidates(run, config.get("levers", [])),
            positive_case=positive_case,
        )

    premium_spec = config.get("premium", {})
    premium_value = metric_value(run, premium_spec, goal_map)
    premium_text = (
        format_manifest_value(premium_value, premium_spec)
        if isinstance(premium_value, (int, float))
        else None
    )
    summary_templates = config.get("summary_templates", {})

    if status == "insufficient_evidence" and focus:
        summary = str(
            summary_templates.get("insufficient_evidence_with_focus")
            or "The current conclusion is conditional."
        )
    elif (
        status in negative_statuses
        and isinstance(premium_value, (int, float))
        and premium_value > 0
    ):
        summary = str(
            summary_templates.get("negative_with_premium")
            or "The current conclusion is conditional."
        ).format(premium=premium_text)
    elif status in positive_statuses:
        summary = str(
            summary_templates.get("positive")
            or "The current conclusion is conditional."
        )
    else:
        summary = str(
            summary_templates.get("default") or "The current conclusion is conditional."
        )

    guidance = {
        "summary": summary,
        "focus": focus
        or str(
            config.get("fallback_focus")
            or "Follow the closest flip condition before broadening the analysis."
        ),
        "deprioritize": deprioritize
        or str(
            config.get("fallback_deprioritize")
            or "Do not spread effort evenly across every estimate."
        ),
        "next_step": next_step
        or str(
            config.get("fallback_next_step")
            or "Resolve the next conclusion-changing variable."
        ),
    }
    tradeoff_template = config.get("tradeoff_template")
    if (
        isinstance(tradeoff_template, str)
        and isinstance(premium_value, (int, float))
        and premium_value > 0
    ):
        guidance["tradeoff"] = tradeoff_template.format(premium=premium_text)
    return guidance


def manifest_guidance(run: dict[str, Any], manifest: dict[str, Any]) -> dict[str, str]:
    config = manifest.get("guidance_config", {}) if isinstance(manifest, dict) else {}
    if not isinstance(config, dict):
        return default_guidance(run)

    mode = config.get("mode")
    if mode == "flip_lever":
        return _flip_lever_guidance(run, config)
    if mode == "goal_cases":
        return _goal_case_guidance(run, config)
    return default_guidance(run)


def default_guidance(run: dict[str, Any]) -> dict[str, str]:
    return {
        "summary": "The current conclusion is conditional.",
        "focus": "Follow the closest flip condition before broadening the analysis.",
        "deprioritize": "Do not spread effort evenly across every estimate.",
        "next_step": "Resolve the next conclusion-changing variable.",
    }


__all__ = [
    "default_guidance",
    "describe_top_flip_lever",
    "first_goal_with_status",
    "format_currency",
    "format_manifest_value",
    "goal_lookup",
    "manifest_guidance",
    "manifest_lever_candidates",
    "manifest_passed_constraint_deprioritize",
    "metric_value",
    "placeholders_are_numeric",
    "rank_flip_levers",
    "render_manifest_template",
]
