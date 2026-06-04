# Product Architecture

This reference captures the productization direction for Decision Proof. The current repository is still a Codex skill plus local scripts; these interfaces describe how to evolve it into a Decision Workspace or API without turning it into a generic advice chatbot.

## Layers

1. **Skill prompt layer**
   - `SKILL.md`
   - Decides when to trigger, what to ask, and how to explain results.

2. **Decision IR layer**
   - `references/decision-ir-schema.md`
   - Stores the user's decision model: question, options, variables, evidence, constraints, proof goals, and recommendation.

3. **Evaluation layer**
   - Python calculators in `scripts/`
   - Computes derived values, constraints, sensitivity, reports, diffs, and option rankings.

4. **Verification layer**
   - Lean or deterministic rule checkers
   - Checks rule closure and invariants; does not check whether real-world estimates are true.

## Domain Pack Shape

Future domains should live under a structure like:

```text
domains/
  car/
    model.yaml
    questions.md
    rules.py
    sensitivity.py
    verifier.lean
    examples/
    tests/
  graduate_school/
    model.yaml
    questions.md
    rules.py
    examples/
    tests/
  job_change/
    model.yaml
    questions.md
    rules.py
    examples/
    tests/
```

Each domain pack should define:

- high-value interview questions
- required variables
- default assumptions
- hard constraints
- soft utility dimensions
- formulas
- sensitivity rules
- output templates
- verifier invariants
- examples and golden tests

Do not make a domain pack until there are at least two realistic examples and one golden test for the domain.

## Run Artifact

Every evaluation should be persistable as a run:

```json
{
  "run_id": "run_001",
  "decision_id": "buy_car_2026_06_04",
  "input_ir_hash": "...",
  "input_ir": {},
  "derived_values": {},
  "proof_state": {},
  "recommendation": {},
  "sensitivity": {},
  "verifier_result": {},
  "created_at": "2026-06-04T00:00:00Z"
}
```

This is the source for Decision Diff.

## Data Model

Prefer storing the full IR JSON as the durable source of truth. Add relational tables only for querying and UI.

### decisions

```sql
decisions
- id
- user_id
- title
- question
- domain
- stakes
- reversibility
- status
- created_at
- updated_at
```

### decision_options

```sql
decision_options
- id
- decision_id
- option_key
- label
- description
- active
```

### decision_variables

```sql
decision_variables
- id
- decision_id
- name
- value_json
- unit
- source
- confidence
- status -- known / unknown / assumption / measured / quoted
- notes
```

### decision_runs

```sql
decision_runs
- id
- decision_id
- input_ir_json
- derived_values_json
- proof_state_json
- recommendation_json
- sensitivity_json
- verifier_result_json
- created_at
```

### decision_evidence

```sql
decision_evidence
- id
- decision_id
- variable_name
- source_type
- value_json
- attachment_url
- notes
- created_at
```

## API Shape

```http
POST /decisions
```

Create a decision.

```http
POST /decisions/:id/interview
```

Generate the next 3-5 high-value questions from the current IR.

```http
PATCH /decisions/:id/variables
```

Update variables.

```http
POST /decisions/:id/evaluate
```

Run evaluator.

```http
POST /decisions/:id/sensitivity
```

Compute flip conditions.

```http
POST /decisions/:id/verify
```

Run verifier or Lean backend.

```http
GET /decisions/:id/report
```

Return the latest report.

```http
POST /decisions/:id/scenarios
```

Create a named scenario.

```http
GET /decisions/:id/diff?from=run_1&to=run_2
```

Return decision diff between two runs.

## Product Guardrails

- Do not hide assumptions.
- Do not collapse confidence into fake precision scores.
- Do not let LLM output final recommendations without an evaluator result when a domain evaluator exists.
- Do not let hard constraint failures be overridden by soft preferences.
- Do not treat unknown as zero.
- Do not expose Lean as the main feature for ordinary users; expose it as a verifier badge.
