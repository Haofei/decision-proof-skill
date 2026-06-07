# Domain Pack Contract (LLM Author Contract)

This document is the interface an **authoring agent** reads to turn a domain
expert's methodology into a Decision Proof domain pack. The expert never writes
JSON; the agent interviews them, drafts the pack, and iterates against the
deterministic engine until it is accepted. It also defines the quality bar every
pack must clear before it is allowed to give recommendations.

It serves three audiences at once:
- the **authoring LLM** — as its capability spec and acceptance criteria,
- the **expert** — as the contract their methodology must satisfy,
- **reviewers** — as the checklist for accepting a pack into the registry.

---

## 0. Status: what is implemented vs. proposed

Be honest about the surface you are authoring against.

- **Implemented today (Tier 0):** a pack is `manifest.json` (declarative) plus a
  `domain.py` that contains the model math in Python. The declarative manifest
  already drives routing, required variables, guidance, next-questions, and the
  dependency/assumption graphs (see `rent_vs_buy`, `graduate_school`).
- **Target authoring surface (Tier 1, NOT yet implemented):** the constraint and
  formula layers described in §5–§6 move into the manifest as data interpreted by
  a closed library of vetted primitives, so a DSL-expressible methodology needs
  **no Python**. Until Tier 1 lands, the agent drafts the declarative parts and a
  developer supplies any bespoke math as a vetted primitive.

Sections marked **(Tier 1)** describe the proposed declarative form. Sections
without a marker describe the engine as it exists now.

---

## 1. The one rule: propose vs. guarantee

The authoring agent **proposes** declarative configuration and **wires vetted
primitives**. It never writes free-form math or arbitrary code. The deterministic
engine — JSON Schema, the domain verifier, the global invariants, and the
expert's golden cases — **guarantees** correctness and decides acceptance.

This is the same division of labour the product uses for decisions themselves
(LLM interviews and explains; the engine computes and enforces guardrails).
Applied to authoring, it is what makes third-party packs **safe** (no arbitrary
code execution) and **trustworthy** (a pack is not "accepted" until it passes the
expert's golden cases and the global invariants).

The agent's job is a loop, not a one-shot emission: draft → validate → run golden
cases → read deterministic errors → revise → repeat until green → show the expert
a human-readable summary for approval.

---

## 2. Anatomy of a domain pack

```
domains/<key>/
  manifest.json     # routing, variables, constraints, formulas, guidance,
                    # questions, dependency + assumption graphs
  questions.md      # the human-facing interview questions
  domain.py         # Tier 0: model math. Tier 1: thin or absent.
  examples/         # >= 2 realistic Decision IRs
  golden/           # input IR + expected outcome cases (the quality gate)
```

`key` must match `^[a-z0-9_]+$`. Schemas the pack validates against live in
`schemas/`: `domain_manifest.schema.json`, `decision_ir.schema.json`,
`proof_goal.schema.json`, `run_artifact.schema.json`.

---

## 3. The Decision IR the pack consumes

A decision is an IR object: `decision` (id, question, type), `options`
(>= 2), and `variables`. The pack is selected when `decision.type` (or
`decision.domain`) matches the manifest's `key` or one of its `decision_types`.

Every variable is an object with **required** fields `value`, `unit`,
`confidence` (0–1), `source`, and an optional `status`
(`known | unknown | assumption`). The cardinal rule:

> **Unknown is never zero.** A variable that is genuinely unknown is written with
> `value: null` and `status: "unknown"`; it opens a proof goal, it is never
> silently treated as 0 or as a default.

The distinction the engine makes:
- **absent** (key not in `variables`) → a default/prior may apply (and must be
  disclosed, §6),
- **explicit null** (`value: null, status: unknown`) → a disclosed unknown that
  opens a goal.

---

## 4. Proof goals: the unit of "proof"

Everything the pack concludes is expressed as proof goals, not scores. A goal is:

```json
{"id": "G2", "claim": "affordability", "status": "...",
 "severity": "...", "reason": "...", "dependencies": ["..."]}
```

- `status` ∈ `closed | failed | open | assumption`
- `severity` ∈ `hard | warning | soft`

Severity is load-bearing — it decides how a failure maps to the recommendation
(§7). Use it deliberately:

- **hard** — a safety/feasibility constraint. A hard failure forbids any positive
  recommendation. (e.g. emergency fund below floor; housing cost above the hard
  ceiling; negative salary premium.)
- **warning** — a real but non-fatal breach, or the decisive soft comparison
  failing. Caps the recommendation at `lean_no` (§7).
- **soft** — passing/anchor goals.

`dependencies` lists the variables a goal rests on; they populate the report's
"Used In" column and must be honest.

---

## 5. Constraints — the declarative goal vocabulary **(Tier 1)**

Express each constraint as data; the engine compiles it to a proof goal. The
closed set of constraint kinds (each backed by a vetted compiler):

- **`threshold`** — `value OP limit` with `OP ∈ {gt, gte, lt, lte}`. Compiles via
  the existing `threshold_goal`: `value`/`limit` `None` → `open`; pass → `closed`;
  fail → `failed` at the declared severity. `value` and `limit` may reference a
  variable, a derived value, a prior, or a literal.
- **`ratio_band`** — a three-way affordability-style band: `<= comfort_limit` →
  closed (soft); `<= hard_limit` → failed (warning); above → failed (hard).
- **`disclosed_boolean`** — a yes/no policy gate (e.g. "loan required while risk
  tolerance is low") with explicit severity per branch.

Each constraint declares: `id`, `claim`, `kind`, its operands, `severity_on_fail`,
`dependencies`, and `reason_closed` / `reason_failed` templates. Exactly one
constraint may be marked `decisive: true` — it drives `positive_case` (§7).

If a methodology needs a constraint shape not in this set, that is a signal to add
a **vetted** kind (developer + review), not to hand-write logic.

---

## 6. Formulas and derived values — the primitive catalog **(Tier 1)**

Derived values are produced by **vetted primitives** the agent references and
parameterizes; it never writes the computation. Two tiers of primitive:

- **Generic primitives** (compose freely): `ratio` (a/b), `difference` (a−b),
  `sum`, `weighted_sum`, `linear_break_even`, `payback` (cost / annual_gain),
  `threshold`. These cover most consulting frameworks (a few weighted factors,
  thresholds, break-evens).
- **Domain-specific vetted primitives** (reference with params, cannot author):
  genuinely algorithmic models, e.g. `rent_buy_break_even` (the monthly net-worth
  simulation in `rent_vs_buy`). These are reviewed code; the agent supplies inputs
  only.

Every numeric derived value MUST declare, in the manifest:

- **`derived_value_dependencies[name]`** — the **required inputs** (must be
  present in the IR; the engine enforces this and forbids unknowns from feeding a
  numeric output).
- **`derived_value_assumptions[name]`** — the **defaulted priors** it depends on.
  These are *disclosed-only*: each must be either explicit in the IR variables or
  surfaced in `assumptions_used`. This keeps the dependency graph complete without
  false-failing whenever a default is in effect.

Priors must resolve safely: an optional prior that is absent **or explicit-null**
falls back to its default (never a crash) and is then listed in `assumptions_used`
so the report's "Default Assumptions" section discloses it.

---

## 7. Recommendation mapping (declared, not coded)

All packs map proof state to one recommendation through the **shared status
ladder**. The order is non-negotiable:

```
baseline?            -> baseline
any hard failure?    -> do_not_recommend
any required-open?   -> insufficient_evidence
any warning failure? -> lean_no            (caution cap)
positive + strong?   -> recommend
positive?            -> lean_yes
otherwise            -> lean_no
```

The pack declares the inputs, not the ladder:
- **`positive_case`** — derived from the `decisive` constraint (e.g. horizon ≥
  break-even).
- **`evidence_quality`** — computed from the listed decision-defining variables'
  `confidence`/`source`: `weak` if any source is `guessed`/`unknown` or min
  confidence < 0.5; `strong` if min confidence ≥ 0.75; else `medium`.
- **`open_required`** — which goals being `open` should block a conclusion.
- **`caution_failed`** — any `warning`-severity failed goal (caps at `lean_no`).

Use only these six states. Never invent new ones.

---

## 8. Sensitivity, guidance, next questions (declarative, implemented)

- **Flip conditions** — the pack declares break-even / threshold outputs ("you
  must stay N years", "max price within budget"). This is the product's edge:
  name the few numbers that flip the conclusion.
- **`guidance_config`** — `mode: goal_cases` (select wording by which goal
  failed/opened, fill flip numbers via placeholders) or `mode: flip_lever` (rank
  levers by proximity to their flip line and narrate the closest). Output fields:
  `summary`, `focus`, `deprioritize`, `next_step`, optional `tradeoff`.
- **`next_questions_config`** — `mode: rules`. Each rule fires on a `when`
  condition (`goal_status`, `variable_unknown`, `low_evidence_variable`,
  `low_evidence_any`, `top_lever`, combined with `any`/`all`) and is ranked by
  value-of-information. The highest-priority question must be the one that most
  moves the conclusion.

---

## 9. The quality contract — what every pack MUST declare

The engine can prove a pack is **self-consistent**; it cannot prove the
methodology is **wise**. These fields are the only defence against a
plausible-but-bad heuristic, and are mandatory for acceptance:

1. **Golden cases** (`golden/`) — at least **3** real decisions the expert has
   judged, each: an input IR + the expected recommendation status + expected key
   derived values (and, ideally, expected failing goal). The pack is rejected if
   any golden case does not reproduce.
2. **Evidence policy** — which variables must be `measured`/`quoted` (not
   `guessed`) for a non-`insufficient_evidence` conclusion.
3. **Escalation boundary** — the explicit conditions under which the pack must
   refuse to conclude (→ `insufficient_evidence`) or must warn off
   (→ `do_not_recommend`). A methodology with no stated boundary is not accepted.
4. **Assumptions disclosure** — every defaulted prior declared in
   `derived_value_assumptions` (§6).
5. **Verifier coverage** — the domain invariants the pack checks (§10).
6. **At least 2 realistic examples** in `examples/`.

> Acceptance bottoms out on the expert's golden cases plus their approval. More
> cases = more trust. The engine guarantees the math and the disclosure; the
> expert guarantees the judgment.

---

## 10. Non-negotiable guardrails (enforced by the global verifier)

The agent must author so that **every** run passes these invariants; they are
checked deterministically and will reject the pack otherwise:

- `input_hash_matches_ir` — the run is about the IR it claims.
- `hard_fail_blocks_positive_recommendation` — a `hard` failed goal can never
  coexist with `recommend`/`lean_yes`.
- `insufficient_evidence_requires_open_goal` — never claim "insufficient" with no
  open goal.
- `derived_values_have_dependencies` — every numeric output declares its inputs.
- `unknown_variables_do_not_feed_numeric_outputs` — a numeric output's required
  inputs must all be present (unknown never silently feeds a number).
- `numeric_outputs_disclose_assumptions` — every defaulted prior behind a numeric
  output is explicit in variables or in `assumptions_used`.
- `option_ranking_respects_status_order` — for comparisons, ranking follows status.

And the design guardrails the agent must not violate:
- do not hide assumptions; do not treat unknown as zero;
- do not let soft preferences override a hard constraint;
- do not present a low-evidence estimate as fact;
- every recommendation must carry flip conditions.

---

## 11. The authoring loop

```
1. INTERVIEW the expert (see §12).
2. DRAFT manifest.json + questions.md + examples/ + golden/.
3. VALIDATE:   python -m decision_proof.cli validate <example.json>
4. EVALUATE every golden case:
               python -m decision_proof.cli report <golden.json>
   - check recommendation status + key derived values == expected
   - check verifier_result.proof_checked and global_verifier_result.ok
5. On any failure, read the structured errors and REVISE. Repeat from 3.
6. SUMMARIZE the pack in plain language (not JSON) and get the expert's
   approval or corrections.
```

A pack is **accepted** iff: schema-valid; all golden cases reproduce; all global
invariants pass; the §9 quality fields are present; ≥ 2 examples and ≥ 3 golden
cases exist.

The machine-checkable parts of this gate are enforced by the release-mode
validator:

```
python -m decision_proof.cli domain-validate <domain_dir> --strict
python -m decision_proof.cli domain-test <domain_dir>
```

`--strict` hard-fails unless the manifest declares `variable_constraints`,
`derived_value_dependencies`, `evidence_policy`, and `escalation_boundary`, and
has ≥ 3 golden cases. `variable_constraints` also powers model-level input
validation (`decision-proof validate`): a value out of its declared range or of
the wrong type (e.g. a 6.5 mortgage rate, a percentage entered as 20, a `$`
string, a zero income) is rejected before it can produce a precise-looking but
wrong result.

---

## 12. The expert interview (meta-interview bank)

The agent runs this to extract a methodology. Ask the fewest, highest-leverage
questions; prefer the ones that change the model's shape.

- **Decision & options** — "What decision is this? What are the realistic
  options, including 'do nothing' / 'wait'?"
- **Hard constraints** — "What would make you refuse to recommend it regardless of
  upside? What are the safety/feasibility floors?" → `hard` constraints.
- **The decisive comparison** — "When the hard constraints pass, what single
  comparison decides it?" → the `decisive` constraint + `positive_case`.
- **The flip variable** — "Which one number, if it moved, would change your
  answer? Where is its break-even?" → flip conditions.
- **Soft factors as willingness-to-pay** — "Translate the non-financial factors
  into 'would you pay $X for it?'" → tradeoff guidance.
- **Evidence policy** — "Which inputs must be real/measured, which can be rough?"
- **Escalation boundary** — "When should the tool say 'I can't answer this yet'?"
- **Golden cases** — "Give me 3 past decisions you judged and the answer you'd
  stand behind, with the numbers." → `golden/`.
- **Priors** — "What reasonable defaults should apply when the user doesn't
  know?" → defaults + `derived_value_assumptions`.

---

## 13. What the agent must NOT do

- write arbitrary Python or any computation outside the vetted primitive set;
- invent thresholds, priors, or weights the expert did not confirm;
- emit a `recommend`/`lean_yes` while any hard goal fails;
- treat an absent or null variable as zero;
- ship a pack with no golden cases, no escalation boundary, or undisclosed
  defaults;
- introduce recommendation states beyond the six in §7.

When in doubt, the agent opens a goal and asks a question — it never guesses a
number into a confident-looking conclusion.
