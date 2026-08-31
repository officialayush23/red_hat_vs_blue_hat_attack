# Agentic Data Contract

Written 2026-08-30, alongside Task #32. Every table below already exists
in `backend/db/migrations/001_core_schema.sql` (plus `005_agentic_contract.sql`
for the weakness_log additions) -- this document is not a schema proposal,
it's the JSON *shape* contract inside the jsonb/text[] columns, so the LLM
strategist (Task #35), the backend, and the frontend all read and write
the same structure instead of three independently-guessed shapes.

Per Principle 12, there is one LLM component wearing two hats -- adaptive
mutation (Section 8 steps 5-6) and composite scenario chaining (Principle
12 itself) -- not two separate agents, and it is structured-output-then-
deterministic-execution, never a live tool-calling loop: the LLM receives
a JSON summary, returns a JSON decision matching a fixed schema below,
and *existing* generator scripts (already-built, ordinary Python
functions) execute that decision. The LLM never touches the database or
Storage directly.

## 1. Adaptive mutation loop (Section 8 steps 5-6) -- `weakness_log`

**Input to the LLM strategist** (or the rule-based fallback per Principle
9), built by the backend from a completed held-out `evaluation_run`:

```json
{
  "run_id": "uuid of the evaluation_run that just completed",
  "per_family_recall": [
    {"attack_family": "account_takeover", "combination": {"device": "new", "location": "trusted", "beneficiary_change": false, "velocity": "gradual_ramp"}, "recall": 0.42, "n_cases": 20},
    {"attack_family": "mule_network", "combination": {"hop_count": 5, "cross_bank_hop": true}, "recall": 0.58, "n_cases": 20}
  ],
  "already_tried_combinations": ["... combinations from prior weakness_log rows for these families, so the strategist doesn't propose a repeat ..."]
}
```

`per_family_recall` is computed by joining `evaluation_results` (this
run's rows) -> `attack_cases` (for `attack_family` and `mutation_params`)
-> grouping by family+combination. Nothing here is a new table; it's a
query, kept here so the shape is agreed rather than reinvented per caller.

**Output from the LLM strategist / rule-based fallback** -- one row
inserted into `weakness_log` per weakness acted on:

```json
{
  "run_id": "the evaluation_run above (where the weakness was found)",
  "attack_family": "account_takeover",
  "combination": {"device": "new", "location": "trusted", "beneficiary_change": false, "velocity": "gradual_ramp"},
  "recall": 0.42,
  "source": "llm",
  "reasons": [
    "Gradual velocity ramp stays under the existing rate-limit feature's window",
    "Trusted-location flag suppresses the location-mismatch signal entirely"
  ],
  "recommended_action": "Generate additional held-out cases with an even slower ramp and a second trusted-but-unusual device",
  "severity": "high",
  "next_strategy": {
    "attack_family": "account_takeover",
    "combination": {"device": "new", "location": "trusted", "beneficiary_change": false, "velocity": "gradual_ramp", "cross_bank_hop": false},
    "generator": "generate_account_takeover_attacks.py",
    "n_cases": 20
  }
}
```

`reasons` / `recommended_action` / `severity` map directly onto
`WeaknessAnalysisPage.jsx`'s existing (currently mock) fields -- no
frontend rework needed once this is wired, just a data-source swap.
`next_strategy.generator` names an *existing* script (Principle 12 -- no
new orchestration surface); the backend calls it with `next_strategy`'s
params, generates round-2 cases, runs a new `evaluation_run`, and writes
that new run's id into **this same `weakness_log` row's
`followup_run_id`** and a short `changes` list (e.g. `["Ramp duration
doubled", "Second trusted device added"]`) -- that's what lets
`AdaptiveMutationPage.jsx`'s before -> after detection-rate delta ("the
demo's central evidence," Section 8 step 6) be a real query:
`weakness_log.recall` (before) vs. the recall computed from
`followup_run_id`'s `evaluation_results` (after), not two independently
asserted numbers.

## 2. Composite scenarios (Principle 12) -- `attack_campaigns` / `campaign_runs`

**LLM strategist output** when composing a multi-stage scenario -- inserted
into `attack_campaigns.stages`:

```json
[
  {"stage": 1, "attack_family": "phishing_scam", "generator": "generate_phishing_attacks.py", "params": {"impersonation_target": "bank_otp"}},
  {"stage": 2, "attack_family": "account_takeover", "generator": "generate_account_takeover_attacks.py", "params": {"triggered_by_stage": 1}},
  {"stage": 3, "attack_family": "mule_network", "generator": "generate_mule_attacks.py", "params": {"triggered_by_stage": 2}}
]
```

Every `generator` value must already exist as a callable script -- the LLM
picks an ordered subset and their params, it does not gain new generative
surface (Principle 12, restated from the spec, not new here).

`campaign_runs.stage_results` mirrors the same stage list with each
stage's outcome appended (`detected: bool`, `case_id`, `evaluation_result_id`);
`weakest_stage` is just the stage name with the lowest per-stage recall,
same computation pattern as section 1.

## 3. Per-case evidence -- `evaluation_results` (already wired, Task #32)

Real shape in production now (`evaluation/supabase_results.py`,
used by all three `eval_*.py` scripts):

```json
{
  "model_signals": [{"model": "phishing_classifier", "score": 0.73}],
  "fused_risk_score": 73.0,
  "decision": "challenge",
  "detected": true,
  "actual_label": "fraud",
  "evidence": ["urgency_phrase_count=2", "url_suspicious_tld=1", "has_url=1"]
}
```

`model_signals` is a list, not a single object, on purpose -- once fusion
(#33-36) combines multiple detectors on one case, each contributes its own
entry here; `fused_risk_score` becomes a real multi-signal fusion instead
of one detector's own score restated (see `TECHNICAL_SPEC.md` Section 6's
"Threshold selection is delegated to this layer" addendum).

## 4. A real naming mismatch, flagged not fixed here

Backend/DB `attack_family` values are `snake_case`
(`account_takeover`, `mule_network`, `document_fraud`, `phishing_scam`,
`voice_scam`, `transaction_fraud`, `synthetic_identity` -- Section 4a's own
taxonomy table). The existing frontend mock data
(`frontend/src/data/mockStore.js`, `attackCatalog.js`) uses `kebab-case`
(`"account-takeover"`). Nothing in the codebase normalizes between them
yet. This must be resolved at the API boundary (#36) -- pick one
canonical form (recommend `snake_case`, matching the DB and Section 4a)
and convert at the edge, not scattered across components -- flagged now so
it isn't discovered mid-wiring.

## 5. What's NOT built yet (honest state, 2026-08-30)

The tables and contract above exist and are ready to receive real data.
The actual LLM-driven (or rule-based) decision loop that *produces*
`weakness_log`/`attack_campaigns` rows is Task #35, not built. It also has
a real prerequisite: Section 8 step 4 ("score the held-out set... per
attack family") needs a working Stage 7 harness
(`evaluation/run_adversarial_eval.py`) for the tabular models
(XGBoost/LightGBM/Autoencoder) -- that script doesn't exist yet either
(confirmed: `dataset.py`'s own docstring says the current val split is
explicitly not that adversarial set). The three pretrained/text detectors
(document_consistency, voice_spoof, phishing_classifier) already produce
real per-family held-out recall via their `eval_*.py` scripts -- those
numbers could seed `weakness_log` manually today as a demo of the shape,
even before #35's automated loop exists.
