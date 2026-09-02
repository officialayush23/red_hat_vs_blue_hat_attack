# FraudShield — Session Handoff (Mastercard Innovation Challenge 2026)

Prepared 2026-08-31, substantially rewritten 2026-09-02 (sections 4 onward --
the previous version described the FastAPI backend, video-KYC and the
frontend rewiring as unbuilt; all three now exist). Purpose: give a fresh model (or a fresh session on any
model) everything needed to keep working on this project with zero lost
context. Paste this whole file as the first message to the new session, or
point it at `docs/SESSION_HANDOFF.md` in the repo.

## 1. What this project is

**FraudShield** — a Kaggle submission for the Mastercard Innovation
Challenge 2026. It's a multi-signal fraud detection system covering
several distinct attack families (tabular transaction fraud, phishing,
voice-cloning/spoofing, document/invoice tampering, and video-KYC identity
impersonation), each with its own detector, fused into a single
risk score and decision (approve / review / challenge / block).

Full architecture lives in `docs/TECHNICAL_SPEC.md` — read that for the
complete spec. This handoff is about *status and what's next*, not a
replacement for the spec.

## 2. The standing rules — non-negotiable, apply to every future turn

These were established over many prior sessions and must not be relaxed:

1. **Nothing is a demo.** Every number reported must come from a real run
   against real (self-generated, but genuinely scored) data. Never
   simulate, estimate, or invent a metric. If something can't run yet
   (missing dependency, broken environment), say so and fix the
   environment — don't fake the output.
2. **Evidence-gate discipline (Principle 11).** Every claim about model
   performance is grounded in an actual script run, with output pasted
   back by the user or read directly. When uncertain about a bug's cause,
   ask for diagnostic evidence (a real traceback, a real directory
   listing) rather than guessing a fix.
3. **Principle 13 — score() takes only the input, never ground truth.**
   Every detector's `score()` / `score_with_evidence()` method signature
   takes a file path or feature vector only. Ground truth (`is_fraud`,
   `actual_label`) is compared *after* scoring, only inside the
   evaluation harness. Enforced by construction throughout
   `backend/evaluation/`.
4. **Threshold-calibration convention.** Decision thresholds are picked
   via `best_f1_threshold()` (in `backend/evaluation/metrics.py`) on
   train/validation data ONLY, then applied unchanged to held-out data.
   Never re-pick a threshold on held-out data — that leaks. This is the
   codebase-wide convention (`run_adversarial_eval.py`'s frozen Stage-5
   thresholds, `eval_fusion.py`, and now `eval_voice_spoof.py` and
   `eval_document_consistency.py` after this session's fixes).
5. **Colab is for one-time heavy-model training/eval only.** Production
   inference never calls Colab. Colab is used when local (Windows)
   GPU inference is broken/unreliable for a specific detector.
6. ~~**Frontend rewiring off `mockStore.js` is explicitly the LAST step.**~~
   **RETIRED 2026-09-02.** This was a sequencing constraint, and it has been
   satisfied: every backend capability is real and evidence-gated, and the
   frontend now reads real Supabase data throughout. Kept here rather than
   deleted so a future session doesn't re-derive it from an old transcript
   and stall the UI work again.
7. **Time-boxed passes per capability:** GNN gets 2-3 passes, voice gets
   2-3, KYC (document) gets 2-3, video-KYC gets 2-3. Don't over-invest in
   one capability at the expense of the others — the user explicitly
   chose (via a decision prompt) to move on from further GNN work to
   voice/KYC/video-KYC.
8. **Report progress after every unit of work** as a running scoreboard:
   *how many attacks can this system successfully detect, defend, and
   adapt against* — stated using real evidence-gate numbers pulled from
   `backend/defend/models/metrics.json`, never from memory or estimate.

## 3. Working conventions that make the above practical

- **`backend/defend/models/metrics.json`** is the single source of truth
  for every model's real metrics. Always read it fresh rather than
  recalling numbers from earlier in a conversation — it changes as new
  evidence-gate runs complete.
- **Device bridge workflow** (when a Windows machine is linked): stage
  files from the device → Read/Edit in the cloud workspace → verify
  (`py_compile`, JSON validity) → `SendUserFile` for a `file_uuid` →
  `device_commit_files` to write back to the real Windows path.
- **Colab notebooks are self-contained.** Don't clone the repo (data
  generators write to `data/generated/`, which is gitignored, so a clone
  wouldn't have the data anyway). Instead, embed every needed backend
  source file directly into a setup cell as `repr()`-encoded string
  literals, verified with `py_compile` before delivery. Binary data
  (images, audio) goes up as a zip via `files.upload()`.
- **Important Colab gotcha, hit twice this session:** overwriting the
  local `.ipynb` file on the user's disk does **not** sync into an
  already-open Colab browser tab. Colab runs whatever was uploaded into
  that tab; a local file edit only takes effect on a *fresh* upload. To
  unblock a live, already-running Colab session, give the user a small
  standalone patch cell that edits the file already on the Colab VM's
  disk directly (`pathlib.Path(...).write_text(...)`), rather than
  telling them to "just re-run" a cell whose source hasn't actually
  changed in that tab.
- **Windows path-separator bug pattern**, hit twice this session in two
  different forms — watch for this again in any future Windows→Colab
  data transfer:
  - PowerShell's `Compress-Archive` writes zip entries with literal `\`
    instead of the zip-spec-required `/`; `zipfile.extractall()` doesn't
    normalize this, so it silently flattens directories. Fix: iterate
    `zf.infolist()` and `.replace("\\", "/")` each entry's filename
    before writing.
  - Any JSON file written by a script that ran on Windows and stores a
    relative file path as a string (e.g. `image_path` in a generated
    case file) will contain `\`-separated paths. `PurePosixPath` doesn't
    treat `\` as a separator, so `REPO_ROOT / c["some_path"]` on
    Linux/Colab silently produces one bogus path component instead of
    real subdirectories. Fix at the point of use:
    `c["some_path"].replace("\\", "/")` before joining.

## 4. Real evidence-gate numbers on hand right now

Treat these as a snapshot — always re-read `backend/defend/models/metrics.json`
(and `model_registry` in Supabase, which `sync_model_registry.py` keeps in step
with it) for the authoritative numbers before reporting a scoreboard. Verified
against the live database on 2026-09-02.

**Cleared the evidence gate:**

| Signal | Model | P | R | F1 | n |
|---|---|---:|---:|---:|---:|
| transaction | lightgbm_adversarial_eval | 0.955 | 1.000 | 0.977 | 1,394,845 |
| transaction | xgboost_adversarial_eval | 0.965 | 0.875 | 0.918 | 1,394,845 |
| behavioral | autoencoder_adversarial_eval | 0.870 | 0.826 | 0.847 | 1,394,845 |
| transaction | fusion_adversarial_eval | 0.969 | 1.000 | 0.984 | 1,394,845 |
| voice | voice_spoof_detector | 0.966 | 0.950 | 0.958 | 204 |
| document | document_consistency_detector | 0.938 | 1.000 | 0.968 | 680 |
| text | phishing_classifier_evidence_gate | 0.882 | 0.875 | 0.879 | 800 |
| identity | video_kyc_detector | 1.000 | 1.000 | 1.000 | **12** |

**Did not clear it:** `gnn_colab_round5_reported` — recall 0.075 (up from
round 4's 0.004, a real improvement to a signal that is still not usable).
Mule-network detection currently rests on sequence features in the tabular
models, not on the GNN. It is shown at its real value everywhere.

**Corpus:** 25,741 attack cases across 7 families, 30,102 scored
`evaluation_results` rows, 7,661 cases carrying playable artifacts.

Two caveats that must travel with these numbers:

- **video_kyc's 1.000 is 12 cases.** It is labelled `provisional` in the
  registry, on the Model Performance page, and in the README. Read it as "the
  pipeline works end to end", never as "validated". `attack_cases` still has
  **no `video_kyc_impersonation` family** — section C of the Colab notebook has
  not completed a corpus-scale run, so there is nothing to backfill yet.
- **phishing's 0.875 is an average across a 100% case and a 36% case.** See
  §4a.

### 4a. The phishing finding (2026-09-02) — half-resolved, and read the correction

The long-open question — is the 0.943-own-validation vs 0.75-held-out drop
overfitting, distribution shift, or a hard split? — is answered from the
persisted per-case rows: **it is none of those.** It is one localised blind
spot. Five of the six generated combinations are caught 100% (Hinglish
included — the obvious suspect, and wrong). One is caught 36%: the low-urgency,
link-free `employer_hr` email, mean score 0.288, which is *below* the mean of
the legitimate messages (0.403). No threshold separates those two, which makes
this the strongest concrete argument in the project for the Section 6 fusion
design.

**What is NOT established is the cause, and an earlier version of this section
claimed it was.** In this corpus every high-urgency case carries a URL and
every low-urgency one carries none — urgency and URL presence are perfectly
confounded — and the classifier has features for both (four of its ten hand
features are URL features). Do not repeat "it is an urgency detector"; the data
cannot support it.

URL presence is not a mutation dimension in `split_policy` at all, it rides
along with the template. **The next experiment is a generation change, not a
retrain:** emit the two missing cells (low-urgency *with* a shortened link,
high-urgency *without* one), re-score, and only then decide what to retrain.

Full working and the correction are at the end of `docs/EVALUATION_RESULTS.md`.

## 5. What exists now (this changed a lot — read before planning)

Three things this handoff previously listed as unbuilt are built:

- **`backend/api/` (FastAPI) exists and is deployed.** Live at
  `https://red-hat-vs-blue-hat-attack.onrender.com`. Railway was the original
  target and was abandoned after free-tier peak-hours deploy blocking on
  `asia-southeast1`; Render is the live one. `GET /version` reports the commit
  actually running, which is the fastest way to answer "is my fix deployed".
- **Video-KYC is built and evidence-gated** (`defend/pretrained/
  video_kyc_detector.py`, facenet-pytorch MTCNN + InceptionResnetV1) — at
  n=12, see the caveat above.
- **The frontend is fully rewired off `mockStore.js`** and reads real Supabase
  data. Deployed on Vercel. Standing rule 6 in §2 is therefore **retired** — it
  described a sequencing constraint that has been satisfied.

Also live: the war room (per-stage progress, per-detector substeps, artifact
playback, a working stop button), a `/simulate` page that scores a visitor's
own uploaded file through the real detectors, and a root `README.md`.

## 6. Pending work, in rough priority order

1. **Section C of the Colab notebook has never completed.** C1 was fixed twice
   on 2026-09-02 (see §7) but the fixed cell has not been run to completion, so
   there are no video-KYC cases in the corpus and the n=12 number stands alone.
   This is the single biggest gap between what the system claims and what it
   has measured.
2. **Verify `/detectors` actually serves.** The live-scoring routes in
   `api/main.py` were syntax- and name-checked but never executed — neither the
   bridge VM nor the cloud sandbox could install FastAPI. Run
   `uvicorn api.main:app --reload` from `backend/` and hit `/detectors` before
   demoing that page.
3. **`npm run build` before any frontend deploy.** The bridge cannot build:
   `node_modules` holds Windows binaries and the bridge shell is Linux.
4. **Low-urgency phishing retrain** (§4a) — the one concrete model improvement
   with a known cause and a known fix.
5. **GNN round 6** — place the round-5 `gnn.pt` at `backend/defend/models/
   gnn.pt` and run `eval_gnn.py` locally as an independent second verification
   of the Colab numbers. Explicitly deprioritized; don't pick it up unless
   asked or everything above is done.
6. **Rotate the Supabase and HF credentials** if not already done — they were
   exposed in a screenshot on 2026-09-01. `.env` was never committed and is
   gitignored, so this is precautionary, but it is not yet confirmed done.

## 7. Bugs worth not re-learning

- **Colab is Python 3.13.** Any pin without a cp313 wheel is unsatisfiable, and
  under `pip install -q` it fails *silently* and exits 0. This burned three
  cells: `numpy<2`, `torch==2.2.2`, `Pillow==10.2.0`. Worse, one attempt ran
  `pip uninstall torch torchvision torchaudio` **before** a pin that could not
  install, leaving a runtime with no torchvision at all. A failed install after
  a successful uninstall is strictly worse than doing nothing. C1 now installs
  `facenet-pytorch --no-deps`, repairs torchvision only if genuinely absent
  (via an explicit torch→torchvision map), and proves health with a real
  forward pass instead of a version assert.
- **`?? 0` defaults turn "never measured" into "measured zero".** Runs stopped
  before the evaluation stage rendered `Detection 0.0%`, `PRECISION 0.00`,
  `0% of taxonomy`. Fixed with `runs.hasEvaluation`; anything rendering a
  metric must check it first.
- **`runs[0]` is the newest run, not the newest run with results.** The sidebar
  keyed its whole Blue Team and Results sections to it, so those pages opened
  empty. Use `useLatestEvaluatedRun()`.
- **`detected` means the prediction was CORRECT**, not "blocked" — a correctly
  approved legitimate transaction counts. Conflating the two inflates the
  number by thousands.
- **`subprocess.run(capture_output=True)` returns nothing until exit.** Long
  stages looked hung. `_run_script_streaming()` in `agent_runner.py` streams
  the per-detector banners the eval/generation scripts already print.
- **Bare globs pick up `.storage_bundle.json`**, the marker `tools/
  storage_sync.py` drops into every directory it manages. Filter
  `not p.name.startswith(".")`. This has caused two separate multi-hour bugs.
- **Windows backslash paths** in JSON written on Windows: `PurePosixPath`
  doesn't split `\`. `.replace("\\", "/")` at the point of use.
- **`git pull --ff-only` exits 128** on this repo — history was rewritten once
  to strip commit trailers, so every SHA changed. Use `git fetch origin main`
  + `git reset --hard origin/main`. The Colab clone cell already does.
- **Backticks in a `git commit -m "…"` string get command-substituted by bash.**
  Write the message to a file and use `-F`.

## 8. Key files to know

- `backend/defend/models/metrics.json` — the scoreboard; single source of truth.
- `backend/orchestration/agent_runner.py` — the closed loop as one run.
  `RunTracker` writes live progress into `campaign_runs.stage_results`.
- `backend/api/main.py` — FastAPI: run control, stop, `/version`, `/detectors`.
- `backend/evaluation/split_policy.py` — which mutation combinations are
  training-allowed vs held-out-only. This file is what makes the "detects novel
  fraud" claim defensible.
- `backend/evaluation/` — `metrics.py` (`best_f1_threshold`),
  `supabase_results.py` (per-case persistence), one `eval_*.py` per family.
- `backend/defend/fusion.py` — ROC-AUC-weighted fusion; bands approve ≤30 /
  review ≤60 / challenge ≤80 / block ≤100.
- `frontend/src/services/api/` — every read goes to Supabase directly with the
  anon key; `jobs.js` is the only module that calls the backend.
- `notebooks/fraudshield_colab_master.ipynb` — sections A–E, GPU work.
- `README.md` — the judge-facing entry point.
- `docs/TECHNICAL_SPEC.md` — the frozen spec, 14 governing principles.
- `docs/EVALUATION_RESULTS.md` — append-only; contains superseded and
  contradictory numbers on purpose. It is the audit trail.

## 9. How to talk to the user about this

The user (Ayush) wants real, working, evidence-gated results — not a demo. They
give real pasted terminal/Colab output as evidence and expect diagnosis
grounded in that evidence, not guesses. When genuinely uncertain about a bug's
cause, ask for a diagnostic (a directory listing, a full traceback) rather than
guessing a fix blind — this has been the effective pattern throughout. When a
guess turns out wrong, say so plainly and move on; don't over-apologize, and
don't quietly re-guess. Several of the worst detours in this project came from
a confident diagnosis that outran its evidence.
