# FraudShield — Session Handoff (Mastercard Innovation Challenge 2026)

Prepared 2026-08-31. Purpose: give a fresh model (or a fresh session on any
model) everything needed to keep working on this project with zero lost
context. Paste this whole file as the first message to the new session, or
point it at `docs/SESSION_HANDOFF.md` in the repo.

## 1. What this project is

**FraudShield** — a Kaggle submission for the Mastercard Innovation
Challenge 2026. It's a multi-signal fraud detection system covering
several distinct attack families (tabular transaction fraud, phishing,
voice-cloning/spoofing, document/invoice tampering, and — not yet built —
video-KYC deepfakes), each with its own detector, fused into a single
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
6. **Frontend rewiring off `mockStore.js` is explicitly the LAST step.**
   Do not touch the frontend until every backend capability is real and
   evidence-gated.
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
for the current, authoritative numbers before reporting a scoreboard.

**GNN / mule_network (round 5, real Colab run, z-score normalization added):**
- IBM AML ROC-AUC: 0.5669 → **0.7532**
- F1: 0.0079 → **0.0258**
- Recall: 0.0045 → **0.0746**
- mule_network cross-domain recall: 0.0000 (n=400) → **0.0010 (n=1000)**
  — still effectively zero; this is a real, structural limitation, not a
  bug: the GNN is trained on IBM AML but evaluated cross-domain on
  self-generated ring_gen.py graphs, with no analogous negative set to
  calibrate a domain-appropriate threshold. Home-turf metrics genuinely
  improved; cross-domain threshold-transfer did not.
- percentile_vs_ibm_aml_test_scores (threshold-independent cross-domain
  signal): 0.9793 → 0.9757 (flat — real but modest signal, ~97-98%,
  didn't move meaningfully round-to-round).
- **Status:** deprioritized behind voice/KYC/video-KYC per explicit user
  decision. `gnn.pt` (round 5) has NOT yet been placed at
  `backend/defend/models/gnn.pt` for a second independent local
  verification pass — open loose end.

**Phishing classifier:**
- Own-validation: 0.943 vs held-out: 0.72 — a known, flagged
  generalization gap (`phishing_classifier_evidence_gate` in
  `metrics.json`). Not yet investigated or worked on this session.

**Voice spoof detector:**
- Threshold-calibration bug fixed (`eval_voice_spoof.py` was hardcoded to
  `threshold=0.5`, now uses `best_f1_threshold` on bonafide + train-split
  spoof only, consistent with the project convention). **Not yet
  independently re-run/confirmed by the user this session** — expected to
  work fine locally (lighter model than the document detector), but no
  real post-fix numbers in hand yet.

**Document consistency detector (PaddleOCR-VL + QR cross-check):**
- Round 1 (hardcoded 0.5 threshold): showed a 25% false-positive rate on
  bonafide documents — plausibly just an uncalibrated cutoff, not a
  detector limitation.
- Round 2 (calibrated threshold via `best_f1_threshold`): **in progress,
  not yet complete.** See Section 5 — this is the single most immediate
  open item.
- Local Windows inference (`paddleocr_env`) is currently broken with a
  distinct new failure (`os error 1455`, a Windows paging-file/virtual-
  memory commitment-limit error, occurring right at first inference after
  a full successful model load) — different from the earlier documented
  DLL-collision class of Windows/PaddleOCR issues. User explicitly chose
  to skip debugging this locally and use Colab instead
  (`notebooks/eval_document_consistency_colab.ipynb`).

**Video-KYC:** 0% built. Needs to be built from scratch — not yet started
at all this session or prior ones per this handoff's knowledge.

**Tabular models (XGBoost, LightGBM, Autoencoder) for transaction_fraud,
account_takeover, synthetic_identity:** established, fused via
`backend/defend/fusion.py` (weights = each model's Stage-5 validation
ROC-AUC, normalized to sum to 1, read fresh from `metrics.json` every
call). No specific numbers restated here — read `metrics.json` directly
for current values rather than trusting this document's memory of them.

## 5. Immediate next step (literally what to do first)

The document-consistency Colab run (`notebooks/eval_document_consistency_colab.ipynb`)
is mid-flight, blocked by a real bug just fixed. Timeline:

1. Colab crashed scoring the first fraud image with
   `FileNotFoundError: '/content/data\generated\document_attacks\held_out\...'`
   — root cause: `image_path` values in the generated case JSON files were
   written with Windows backslash separators (the data generator ran on
   Windows), which Linux/Colab's `PurePosixPath` doesn't split on.
2. Fixed in three places: the real repo's
   `backend/evaluation/eval_document_consistency.py` (committed to the
   real machine via the device bridge), the Colab notebook's embedded
   copy of that same script (also committed), and — because the user's
   live Colab tab doesn't pick up the local `.ipynb` edit automatically —
   a standalone one-off patch cell was handed to the user to run directly
   in their live Colab session, patching the already-written file on the
   Colab VM's disk in place (no re-upload/reinstall/re-upload-zip needed).
3. **As of this handoff, the user has NOT yet confirmed the patch cell
   ran successfully or that the eval script completed.** This is the
   very next thing to check when the conversation resumes: ask for /
   read the output of (a) the patch cell confirming the line was fixed,
   and (b) the re-run of the "Run the real evidence-gate script" cell.
4. Once it succeeds, the notebook's last cell prints the recorded
   `document_consistency_detector` JSON entry — same pattern used for the
   GNN round 5 merge: the user pastes that JSON back, and it gets merged
   into the real `backend/defend/models/metrics.json` (preserving all
   other entries, following the existing `_colab_round5_reported`-style
   naming convention already used for the GNN).
5. After that, update `docs/EVALUATION_RESULTS.md` if the eval script's
   own `_append_results_md` didn't already do it via the Colab run (it
   should have — check).

## 6. Full pending task list, in rough priority order

1. **Finish document_consistency round 2** (Section 5 above) — get real
   post-calibration recall/precision/FPR/threshold numbers, merge into
   `metrics.json`.
2. **Get `eval_voice_spoof.py` run locally** and confirm the threshold-fix
   didn't break anything real — not yet confirmed this session.
3. **Video-KYC — build from scratch.** Nothing exists yet. Needs its own
   2-3 time-boxed passes per the standing convention (Section 2, item 7).
   Figure out what "attack" means for this family (likely deepfake face
   swap / synthetic video during a KYC liveness check), what pretrained
   model or approach to use (Principle 6 precedent: prefer pretrained
   inference over training from scratch where a good pretrained option
   exists, as was done for voice_spoof and document_consistency), build
   the detector, generate attack data, evidence-gate it.
4. **Phishing classifier generalization gap** (0.943 own-val vs 0.72
   held-out) — flagged, not investigated. Worth a pass: is this overfit,
   a distribution-shift issue, or a genuinely hard held-out split?
5. **GNN round 6 (if resumed later)** — place the round-5 `gnn.pt` at
   `backend/defend/models/gnn.pt` and run `eval_gnn.py` locally as an
   independent second verification pass of the Colab numbers. Currently
   deprioritized behind the above per explicit user decision — don't
   pick this back up unless the user asks or the above are done.
6. **`backend/api/` (FastAPI) build** — doesn't exist yet. Deprioritized
   behind finishing all detection capabilities first.
7. **Frontend rewiring off `mockStore.js`** — explicitly the LAST step of
   the whole project. Do not start this early.
8. **Ongoing, every step:** report progress as the running "attacks
   detected/defended/adapted against" scoreboard using real numbers from
   `metrics.json`, after each unit of work — this is a standing
   instruction, not a one-time task.

## 7. Key files to know

- `backend/defend/models/metrics.json` — the scoreboard; single source of
  truth for every model's real evidence-gate metrics.
- `backend/defend/fusion.py` — real multi-signal fusion for the four
  tabular attack families; ROC-AUC-weighted, decision bands (approve
  ≤30 / review ≤60 / challenge ≤80 / block ≤100).
- `backend/evaluation/` — `metrics.py` (shared metric computation +
  `best_f1_threshold`), `supabase_results.py` (per-case persistence for
  the evidence viewer), and one `eval_*.py` per detector family.
- `backend/evaluation/eval_document_consistency.py` /
  `backend/evaluation/eval_voice_spoof.py` — both just had their
  threshold-calibration bug fixed this session (were hardcoded to 0.5).
- `backend/defend/pretrained/document_consistency_detector.py` —
  PaddleOCR-VL + QR cross-check logic; Windows-local inference currently
  broken (`os error 1455`), Colab is the working path.
- `notebooks/train_gnn_mule_network.ipynb` — GNN training, round 5 done.
- `notebooks/eval_document_consistency_colab.ipynb` — the notebook
  actively being debugged right now; see Section 5.
- `docs/TECHNICAL_SPEC.md` — full system architecture and spec.
- `docs/EVALUATION_RESULTS.md` — human-readable log of evidence-gate
  results, auto-appended by each eval script.
- `docs/FUTURE_INTEGRATIONS.md` — documents the PaddleOCR Windows
  DLL-collision history and other deferred/future work.
- `.gitignore` — note `data/generated/` is gitignored (all generated
  attack data/images regenerate from scripts in `generate/`, not
  committed) and there's a leftover `colab_document_fraud_package.tar.gz`
  entry marked safe to delete (an earlier, now-superseded Colab transfer
  package from 2026-08-30).

## 8. How to talk to the user about this

The user (Ayush) wants real, working, evidence-gated results — not a
demo. They give real pasted terminal/Colab output as evidence and expect
diagnosis grounded in that evidence, not guesses. When genuinely
uncertain about a bug's cause, ask for a diagnostic (a directory listing,
a full traceback) rather than guessing a fix blind — this has been the
effective pattern all session. When a guess turns out wrong, acknowledge
it plainly and move on, don't over-apologize.
