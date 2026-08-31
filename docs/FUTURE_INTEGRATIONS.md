# Future Integrations

A running list of upgrades that were deliberately scoped OUT of the
hackathon build, not overlooked. Each entry exists because we considered
it, judged it a real improvement, and judged the timing wrong given the
deadline -- not because the idea was rejected.

Process (2026-08-30, per Ayush): entries are added only when explicitly
agreed in conversation, not unilaterally. When something looks like a good
addition mid-task, it gets flagged and asked about first; it lands here
only on confirmation.

---

## 1. VLM reasoning layer for document_fraud detection

**What:** A separate vision-language model (Qwen-VL / MiniCPM-V class, or
similar compact open VLM) added as a third evidence source alongside
PaddleOCR-VL's structured extraction and the QR cross-check --
visual-anomaly reasoning (typography/layout inconsistency, seal/logo
mismatches, suspicious field placement), document-type classification, and
cross-modal reasoning over the whole image rather than just extracted text.

**Why it's a real improvement:** OCR + QR cross-check only catches
inconsistencies in the fields it extracts. A VLM can reason over things
plain extraction can't: whether a document visually resembles its claimed
template, whether a region looks pasted-in, relationships between multiple
visible elements. Explicitly scoped as an evidence generator feeding a
deterministic decision layer, not as the fraud-score source itself (VLM
outputs are not trustworthy enough to be the classifier on their own --
this matches published findings on hybrid OCR+VLM document pipelines
outperforming direct VLM extraction; see the discussion this decision came
out of, 2026-08-30).

**Why deferred:** A general-purpose VLM (Qwen-VL/MiniCPM-V) is
torch-based, unlike PaddleOCR-VL which stays on paddlepaddle -- adding it
risks the same category of integration cost voice_scam's Chatterbox pivot
paid today (a full day: segfaults, a Windows pagefile limit, an HF token
mismatch, a reference-audio bug), on top of six other Phase 2-5 tasks
still pending before the Aug 31 deadline. Not a rejection of the idea, a
sequencing call under a hard deadline.

**Prerequisite for picking this up:** Almost certainly its own venv (same
pattern as `requirements-voice-gen.txt`) given the likely torch-version
conflict with the existing `torch==2.13.0+cu130` install; budget real time
for a first-integration debugging pass, since that's been the actual cost
every time so far, not the model choice itself.

**Also considered and folded into the same "later" bucket, not built now:**
- Deterministic image-forensics features (compression-inconsistency,
  copy-paste region detection, resampling/noise artifacts, a tamper
  heatmap for the frontend) -- legitimate on its own, but credible forensic
  feature engineering is its own scope, and a rushed/fake-looking version
  would violate this project's own evidence-gate discipline worse than not
  having it.
- Cross-document / KYC identity matching (PAN/Aadhaar/bank-statement/
  invoice/customer-profile consistency) -- the synthetic_customers table
  (Section 4b-i) is now populated (generate/synthetic_customers.py,
  2026-08-30) and document_fraud cases already carry a customer_id and
  compare beneficiaries against that customer's trusted vendor list, so
  the prerequisite this item was blocked on is done. Full cross-document
  matching against real-shaped identity documents (Aadhaar/PAN/bank
  statements as their own artifact types, not just invoices) is still
  deferred -- see item 2 below for the fuller threat-landscape scoping
  this connects to.

---

## 2. GPU inference for PaddleOCR-VL and voice generation

**What:** Run the document_fraud PaddleOCR-VL pipeline on GPU instead of
CPU, and (separately, still fully deferred) point Chatterbox's
voice_gen_env torch install at a CUDA build instead of CPU for voice_scam
generation -- the RTX 3050 6GB laptop GPU already used for the
transaction-model torch stack sits idle for both of these today.

**Why it's a real improvement:** PaddleOCR-VL is a 0.9B-parameter
vision-language model; CPU inference is the actual bottleneck on the
document_consistency_detector evidence-gate run -- confirmed with a real
number, not assumed: 373.5s for a single predict() call on this machine
(2026-08-30). At that rate a 120-image run is ~12.5 hours, not viable
before the deadline. GPU inference should cut that to minutes.

**What actually happened (2026-08-30) -- this item's original plan was
wrong about one thing, corrected here rather than silently reworded:**
The original plan was to install paddlepaddle-gpu straight into the main
`red` venv, on the theory that paddlepaddle and torch are independent
frameworks with no version-pin conflict. That's true for the CPU build
(it ships no CUDA DLLs). It is NOT true for paddlepaddle-gpu: it bundles
its own cudnn/cublas DLLs (nvidia-cudnn-cu12, nvidia-cublas-cu12, etc.)
that share filenames with torch's bundled CUDA DLLs (e.g.
cudnn_cnn64_9.dll) but aren't ABI-compatible builds. Windows' DLL loader
can resolve a dependency from the wrong framework's bundle when both are
importable in the same venv/process, producing
`[WinError 127] The specified procedure could not be found` on the first
real inference call -- reproduced exactly on this machine, matches a
public report (github.com/PaddlePaddle/PaddleOCR/issues/14904). Same
class of Windows cross-framework DLL conflict as the Chatterbox/torch
pivot documented in item 1 above. Fix applied: full venv isolation
(`paddleocr_env`, requirements-paddleocr-gpu.txt), same pattern as
requirements-voice-gen.txt -- a venv that never installs torch has
nothing for paddlepaddle-gpu's DLLs to collide with. document_fraud
evaluation now runs there, not in the main `red` venv.

**Forward-looking implication for Task #36 (real API + frontend), not
solved here, just flagged so it isn't rediscovered cold:** the isolation
fix above works for a one-off evidence-gate script, but the future API
server (Task #36) will need to serve predictions from BOTH torch-based
detectors and this PaddleOCR-VL detector, likely in the same request
lifecycle. Two separate venvs can't both be "the running server process."
Options to weigh then, not now: run document_fraud detection as a
subprocess/sidecar the main API shells out to (keeps the isolation, adds
IPC overhead and complexity); find a paddlepaddle-gpu build whose bundled
CUDA DLLs are versioned/namespaced to avoid the collision (would need
real verification, not assumed); or accept CPU-only PaddleOCR-VL in the
live API path specifically, GPU only for offline batch evaluation/
regeneration (CPU's ~373s/call is bad for a live demo request, but the
lazy-load-per-API-call design already agreed for Task #36 -- separate
tab, explicit "may be slow" popup -- exists precisely to make a slow,
occasionally-unavailable heavy-model call an honest, expected UX rather
than a bug).

**Why not done everywhere yet:** document_fraud's GPU switch is done
(isolated venv, above). voice_scam's Chatterbox venv is a separate,
already-closed, evidence-gated pipeline (`voice_gen_env`, pinned
torch==2.6.0) -- reinstalling its torch as a CUDA build is a second,
independent dependency-risk pass (the CPU choice there was deliberate,
see voice_gen.py's docstring) and isn't worth touching mid-deadline when
it already produced real numbers. Logged here explicitly so it gets done
properly later, deadline or not (per Ayush, 2026-08-30) -- not dropped
once the hackathon submission is in.

**Prerequisite for picking this up (voice_gen_env only):** Confirm the
voice_gen_env's installed torch build
(`python -c "import torch; print(torch.cuda.is_available())"` inside that
venv) before reinstalling anything -- it may already be a CUDA build that
just hasn't been exercised on GPU hardware, in which case this is a
zero-risk device= flip, not a reinstall. Note it will face the exact same
class of Windows DLL question as paddlepaddle-gpu did if voice_gen_env
ever also needs a non-torch GPU framework alongside it -- not the case
today (voice_gen_env is torch-only), so not a live risk yet, just the
same lesson applying in advance.
