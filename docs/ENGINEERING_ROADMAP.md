# Engineering roadmap — what FraudShield already proves, and what it doesn't

Written 2026-09-02, against the repository as it actually stands, not against
what it aims to be. Three lenses: **software developer**, **ML engineer**,
**agentic AI engineer**. Every gap names a real file or a real incident from
this project, because a gap you can point at is one you can close.

Read the ordering at the end before starting anywhere.

---

## 0. What this project already proves

Worth stating first, because it changes what the gaps mean. Most portfolio
projects report a number and stop. This one:

- **Generates its held-out test set after freezing the models**
  (`evaluation/split_policy.py`), from mutation combinations excluded from
  training. That is the difference between claiming "detects novel fraud" and
  being able to defend it.
- **Structurally prevents label leakage.** `score()` takes a file path.
  Ground truth meets a prediction only inside the evaluation harness.
- **Publishes results that got worse.** `docs/EVALUATION_RESULTS.md` is
  append-only and contains superseded and contradictory numbers on purpose.
- **Ships real infrastructure**: FastAPI + subprocess orchestration, Postgres
  with RLS and foreign keys, a React front end, two live deployments.
- **Has a documented history of finding its own dishonesty.** In one day:
  stale-scoreboard reads presented as this run's results, `?? 0` defaults
  turning "never measured" into "measured zero", and a skipped step exiting 0
  so it read as a pass. One bug class, three disguises.

That last point is the most valuable thing here and the least likely to be on a
CV. Keep it.

---

## 1. Software developer

### 1.1 The security gap — fix this first

`backend/api/main.py` has **no authentication on any endpoint**. There is no
`Depends`, no API key check, no `Authorization` header anywhere in the file.
That means anyone who knows the URL can:

- `POST /runs/start` — **spawn a Python subprocess on your server**, repeatedly.
- `POST /detectors/{id}/score` — upload files (capped at 25MB each, uncapped in
  count) and drive model inference.
- `POST /data/hydrate` — trigger large downloads from your Storage bucket.

The deployment is public. This is not a theoretical finding; it is remote
compute execution by unauthenticated strangers, and it is the single thing most
likely to end an interview badly if a reviewer notices it before you mention it.

**What to learn:** API authentication patterns — a shared secret in a header is
enough here, via a FastAPI dependency. Then rate limiting (`slowapi` or a
reverse-proxy rule), and request size limits. Understand the difference between
authentication (who), authorization (what they may do), and rate limiting (how
often) — they are three separate controls and this API has none of them.

**First task:** one `require_api_key` dependency applied to every mutating
route, with the key in `.env` and the frontend sending it. An hour, and it
removes the worst liability in the repo.

Related: you leaked `SUPABASE_SERVICE_ROLE_KEY` in a screenshot on 2026-09-01.
`.env` was correctly gitignored and never committed — the process worked — but
confirm the rotation actually happened. Learn how secrets leak in practice:
screenshots, logs, error messages, client bundles. Note that anything prefixed
`VITE_` is compiled into the public JavaScript, which is why the anon key
belongs there and the service-role key never does.

### 1.2 There are no tests

Not one test file. No `pytest.ini`, no `pyproject.toml`, no CI workflow. For a
developer role this is the largest single gap, and it is the cheapest to close
because this codebase has unusually good test candidates:

| What to test | Why it matters here |
|---|---|
| `split_policy` — no held-out combination appears in training | An **automated leakage test**. This is the project's central claim; asserting it in code is a strong signal. |
| `fusion.decision_for` band boundaries | Off-by-one at 30/60/80 changes every decision label. |
| `detected` vs `decision` | This exact confusion produced a wrong dashboard tile. A test pins the semantics. |
| `best_f1_threshold` | Calibrate-on-train-only is a convention; make it enforced. |
| `_features_for` vs `_score_case_reference` | Already has a `--verify-fast-path` flag — promote it to a test with a golden fixture. |
| `explain_persistence_failure` | Pure function, four branches, trivially testable. |

**What to learn:** `pytest` (fixtures, parametrize, `tmp_path`), what makes a
test valuable rather than decorative (test behaviour and invariants, not
implementation), and property-based testing with `hypothesis` — the
`unique_out_cp` / `in_port` vectorisations were verified over 2,000 random
graphs, which is exactly hypothesis's job.

**First task:** `backend/tests/test_split_policy.py` asserting the leakage
invariant. One file, and it tests the thing the whole project rests on.

### 1.3 No CI, no linting, no formatting

`frontend/eslint.config.js` exists; the Python side has nothing. There is no
GitHub Actions workflow, so nothing runs on push — including
`tools/check_undefined_names.py` and `tools/check_jsx_imports.py`, which were
written *because* a missing `import os` silently destroyed a run's per-case
persistence.

**What to learn:** `ruff` (linter and formatter in one, fast, sane defaults),
`mypy` or at least consistent type hints, `pre-commit` hooks, and GitHub Actions
basics — triggers, jobs, caching.

**First task:** a workflow that runs both existing checkers plus `ruff check` on
every push. Half an hour, and it makes the discipline visible on the repo page.

### 1.4 Error handling swallows too much

The pattern `except Exception as exc:` followed by a printed message appears
throughout. It is deliberate in places — a persistence failure shouldn't kill a
run that produced real metrics — but it is applied uniformly to cases that
differ. A `NameError` in our own code and a Postgres foreign-key rejection are
not the same event, and until `explain_persistence_failure` was added they got
the same advice.

**What to learn:** exception taxonomy — which errors are recoverable (transient
network), which are the caller's fault (bad input), which are yours (a bug).
Custom exception classes. When to re-raise. Why bare `except` hides bugs, and
why "fail loudly at the boundary, handle specifically inside" is the usual rule.

### 1.5 `print()` is not logging

Every diagnostic in the backend is a `print()`. That is why the subprocess
"tail" captured the JSON summary instead of the error — there were no levels to
filter by, so the last 20 lines were whatever happened to be last.

**What to learn:** Python's `logging` module — levels, handlers, formatters,
`logger = logging.getLogger(__name__)` per module. Then structured logging
(`structlog`, or JSON lines) so a log can be queried rather than read. This
directly fixes a bug you actually hit.

### 1.6 In-process state breaks past one worker

`_eval_runs`, `_gen_runs`, `_orch_runs`, `_hydrate_runs` and `_DETECTOR_CACHE`
are module-level dicts. Your Render logs show `Setting WEB_CONCURRENCY=1 by
default` — the app works **only because there is exactly one worker process**.
Add a second and half the status polls hit a worker that has never heard of the
run.

**What to learn:** why shared mutable state is the hard part of scaling a web
service; where state should live instead (Postgres, Redis); the difference
between stateless request handling and a background-job queue (Celery, RQ, or
Postgres-backed). You are already halfway there — `campaign_runs` is the real
source of truth and the dicts are a cache in front of it.

### 1.7 Front-end gaps

No tests, no error boundaries, no TypeScript. A thrown error in one component
blanks the page. `getGeneratedCombinations` fetches up to 1,000 rows and chunks
result lookups by 200 — correct, but the 1,000 cap is silent, so a large family
is quietly truncated with no indication.

**What to learn:** React error boundaries; React Testing Library; TypeScript (or
at least JSDoc types) — most of this session's bugs were shape bugs
(`run.stageFailures` undefined, `mapRow` not exposing `artifacts`) that types
catch for free. Then pagination as a first-class UI concern: a truncated list
must say it was truncated.

---

## 2. ML engineer

### 2.1 No baselines

XGBoost reports F1 0.918. Against what? There is no logistic-regression
baseline, no majority-class baseline, no rules baseline. "Our model gets 0.918"
is not a result; "our model gets 0.918 where a tuned logistic regression gets
0.74 and a three-rule heuristic gets 0.61" is.

**What to learn:** baseline discipline — always ship the dumbest thing that
could work, first. `sklearn.dummy.DummyClassifier` for the floor. Learn to be
suspicious of a strong number with nothing to compare it to.

### 2.2 Calibration — you have two failures and no fix

This project has produced **two independent threshold-transfer failures**:

- `phishing_classifier`: `best_f1_threshold` on difraud validation → **39% FPR**
  on our generated data.
- `gnn`: threshold 0.8222 calibrated on IBM AML lands at the top of a collapsed
  0.61–0.82 score distribution on our rings.

Two unrelated detectors, same pattern. That is a thesis, not a footnote, and the
architectural response already exists (fusion owns the decision,
`TECHNICAL_SPEC` §6). What's missing is the ML response.

**What to learn:** probability calibration — Platt scaling, isotonic regression,
`sklearn.calibration.CalibratedClassifierCV`; reliability diagrams; Brier score;
and why a well-ranked score (ROC-AUC) and a well-calibrated one are different
properties. This is a senior-level topic you have already earned the right to
talk about.

### 2.3 An experimental-design flaw in your own data

In the phishing corpus, **every high-urgency case carries a URL and every
low-urgency one carries none**. Urgency and URL presence are perfectly
confounded, so the 36%-vs-100% caught-rate gap cannot be attributed to either.
Four of the classifier's ten hand features are URL features.

This is a genuinely good thing to have found in your own work, and the fix is
free: URL presence is not a mutation dimension in `split_policy` at all — it
rides along with the template.

**What to learn:** confounding and experimental design; why you vary one factor
at a time; factorial designs. Ablation studies — drop the URL features, retrain,
re-measure, and the question answers itself.

### 2.4 Error analysis is one-off, not systematic

The phishing per-combination analysis was done by hand in SQL. It found the
single most important fact about that detector. Nothing does this routinely for
the other six.

**What to learn:** systematic error analysis — slice-based evaluation, confusion
matrices per segment, and the habit of asking "where does this fail?" before
"how accurate is it?". Look at `sliceline` or just disciplined `groupby`. The
per-combination caught-rate table now in the Attack Library is the right shape;
generalise it.

### 2.5 No experiment tracking or reproducibility discipline

`metrics.json` is a hand-rolled scoreboard — and its weakness caused a real
incident: the orchestrator read it and reported *earlier runs'* numbers as this
run's results, because nothing recorded which run produced which entry. Seeds
exist but dependency versions are not locked, and three separate venvs exist
because of conflicts that were solved by isolation rather than resolution.

**What to learn:** MLflow or Weights & Biases (runs, params, metrics, artifacts,
lineage); `pip-tools` or `uv` for lockfiles; `DVC` for data versioning if you
want to go further. The concept that matters: **an experiment is
(code, data, params, environment) → result**, and if any of the four is
unrecorded the result is not reproducible.

### 2.6 The GNN needs a decision

It is currently a liability presented honestly. Either run the normalization
check now documented in `EVALUATION_RESULTS.md` — cheap, and the eval is 22×
faster — or promote the write-up to a deliberate negative result. "I diagnosed a
transfer failure down to a collapsed score distribution and showed no threshold
could fix it" is a strong story. An open TODO is not.

**What to learn:** domain shift and transfer learning; when fine-tuning beats
transferring; how to recognise a representation problem versus a capacity or
calibration problem — you now have a worked example of exactly that distinction.

---

## 3. Agentic AI engineer

### 3.1 The strategist is unmeasured — this is the biggest opportunity

`evaluation/llm_strategist.py` chooses attack strategy, and Principle 9
guarantees the system degrades to a rule-based selector without it. **You have a
control group built into the architecture and have never run the experiment.**

Run N adaptive rounds with the LLM selecting mutations, N with the rule-based
selector, same seeds, and compare weakness-discovery rate. If the LLM wins, that
is a real agentic result with evidence behind it. If it loses, that is an
equally publishable honest finding — and this project's whole identity is
measuring things rather than asserting them.

**What to learn:** agent evaluation — the hardest and most in-demand part of
agentic work. Task success rate, cost per success, variance across seeds. Read
about LLM-as-judge and its failure modes. Understand why "it seemed to pick good
mutations" is not evidence.

**This is the single highest-value item in this document.**

### 3.2 The orchestration is a pipeline, not an agent

`agent_runner.py` is a fixed 8-stage script. It is *honestly labelled* —
Principle 12 says so explicitly, which is to your credit — but a role advertising
"agentic AI" means tool-use loops, planning, and recovery. The gap shows most
clearly in failure: when a stage fails, the run continues to the end and reports
anyway. `run_b1b555224c` spent 926 seconds discovering that a file it needed was
missing, then finished and reported results.

A real agent would notice the missing artifact, decide to rebuild it, and
continue — which is precisely the fallback later added by hand. **Encoding that
decision as something the orchestrator makes at runtime, rather than something
you hardcoded afterwards, is the difference.**

**What to learn:** the plan → act → observe → replan loop; ReAct; retries with
backoff; compensating actions; when to stop rather than continue degraded. Then
read your own `_hydrate_if_needed` — it is already a small version of this.

### 3.3 No guardrails on LLM output

The strategist's output is parsed and used. There is no schema validation, no
retry on malformed output, no bound on what it may propose.

**What to learn:** structured output — JSON mode, function calling, Pydantic
validation of model output, retry-on-invalid. Prompt injection as a real threat
model: your system reads generated attack text, and an LLM in that loop is an
attack surface. This is directly relevant to a fraud-security product.

### 3.4 No cost or token accounting

Nothing records what the LLM costs per run. In production agentic systems this
is a first-class metric.

**What to learn:** token accounting, caching, and the cost/quality trade-off of
model choice per task. "Cost per weakness discovered" would be a genuinely
impressive metric to report.

### 3.5 No memory across runs

Each run starts cold. The strategist cannot learn that a mutation direction was
already tried and failed.

**What to learn:** agent memory — episodic versus semantic; when a vector store
earns its keep versus a plain table (here, a table almost certainly wins). Note
that `weakness_log` in the schema is already most of what is needed.

---

## 4. What to do, in order

Ordered by value per hour, not by topic.

1. **API authentication.** One hour. Removes the worst liability in the repo.
2. **`test_split_policy.py`** — the leakage invariant. One file. Tests the
   claim everything else rests on.
3. **CI workflow** running the two existing checkers plus ruff. Half an hour,
   permanently visible.
4. **The strategist A/B.** The headline result for agentic work, and you already
   have the control group.
5. **A logistic-regression baseline** for the tabular models. Cheap, and it
   either strengthens your numbers or teaches you something.
6. **URL as a mutation dimension**, then re-score phishing. Unblocks the
   confound and the training-data work.
7. **Calibration** — isotonic or Platt on one detector, with a reliability
   diagram. Turns a known weakness into demonstrated judgment.
8. **Replace `print` with `logging`.** Mechanical, and fixes a real bug class.
9. **The GNN decision** — normalization check, then fix or write up as a
   negative result.
10. **Experiment tracking** (MLflow). Do this once the above are done; it pays
    off over the next project, not this one.

Items 1–3 are a weekend. They change how the repository reads to a stranger more
than items 4–10 combined.

---

## 5. How to talk about this

The strongest thing here is not any single number — it is that the project
**catches itself being wrong**, repeatedly, and writes it down. Three examples
worth having ready:

- **"Our detection rate was 100% and it was a lie."** Stages failed, the
  orchestrator read a scoreboard containing earlier runs' entries, and the run
  reported a clean 100%. Explains the difference between a number being real and
  a number being *this run's*.
- **"Two detectors, same failure, and it's not the models."** Two independent
  threshold-transfer failures led to an architectural decision — no single
  signal owns the decision. Shows you can generalise from incidents to design.
- **"I found a confound in my own data."** The urgency/URL confound, found while
  building a demo, corrected in three documents including one already published.
  Shows the thing interviewers actually probe for: what do you do when you
  discover you were wrong.

Do not lead with F1 scores. Lead with the fact that you can tell which of your
numbers you trust, and why.
