# FraudShield

**A closed-loop adversarial fraud detection system: a Red Team that generates real fraud artifacts, a Blue Team that scores them blind, and a mutation engine that attacks whatever the Blue Team was weakest at.**

Built for the **Mastercard Innovation Challenge 2026** — AI Defense Lab for Payment Security.

- **Live prototype:** https://frontend-rho-nine-z4p151iebp.vercel.app
- **API:** https://red-hat-vs-blue-hat-attack.onrender.com (`/health`, `/version`)
- **Frozen spec:** [`docs/TECHNICAL_SPEC.md`](docs/TECHNICAL_SPEC.md) · **All recorded numbers:** [`docs/EVALUATION_RESULTS.md`](docs/EVALUATION_RESULTS.md)

---

## The one idea

Most fraud demos show a model scoring a static test set. The number is real; the claim it supports ("this detects novel fraud") is not, because the test set came from the same distribution as the training set.

FraudShield closes the loop instead:

```
Red Team  ──generates──▶  real artifacts        (audio, invoice images, message text,
   ▲                       + transaction rows     transaction sequences, video pairs)
   │                              │
   │                              ▼
mutation                   Blue Team scores them BLIND
engine                     (never sees attack_family, is_fraud, or campaign_id)
   │                              │
   │                              ▼
   └──weakest family──── evaluation harness compares score vs. ground truth
```

Three properties make the loop mean something, and each one is enforced in code, not just described here:

1. **The held-out set is generated after the models are frozen**, from mutation-parameter combinations excluded from training (`backend/evaluation/split_policy.py`). A model has genuinely never seen these combinations.
2. **Detectors never receive labels.** `DocumentConsistencyDetector.score()` and `VoiceSpoofDetector.score()` take a file path and nothing else. Ground truth meets a prediction only inside the evaluation harness, after the detector has already committed to a score.
3. **No number is displayed unless a real run produced it.** A model with no evidence-gate run ships as `experimental` and is labelled as such in the registry, the dashboard, and the walkthrough. This is the project's hardest rule and the one that cost the most work.

---

## What the Red Team actually produces

Not scores. Files. Every attack leaves a persistent, inspectable artifact you can open in the UI and play, view, or read.

| Family | Cases in corpus | Artifacts | What is generated |
|---|---:|---:|---|
| `transaction_fraud` | 7,760 | — | Deterministic transaction rows (amounts, timing, balances) |
| `mule_network` | 5,160 | 5,160 | Multi-hop relay sequences across accounts and banks |
| `synthetic_identity` | 5,160 | — | Fabricated identity + application patterns |
| `account_takeover` | 5,160 | — | Session/behavioural takeover sequences |
| `phishing_scam` | 1,132 | 1,132 | Full message text with real URL shapes |
| `document_fraud` | 1,012 | 1,012 | Tampered invoice images + their QR payloads |
| `voice_scam` | 357 | 357 | Chatterbox-cloned audio against a registered reference voice |

**25,741 attack cases · 30,102 scored evaluation rows** (live counts from Supabase at the time of writing).

The LLM never writes a financial value. It selects *strategy* — which family to attack next, which mutation direction to push — and deterministic Python generates every amount, balance and timestamp. Disable the LLM entirely and the system degrades to a rule-based mutation selector; it does not fail.

---

## What the Blue Team detects, and how strong that evidence actually is

Every headline number below is paired with its sample size, because "100% on 12 samples" and "97.7% on 1.39M rows" are both real numbers and only one of them means anything. This table is generated from the same `model_registry` rows the dashboard reads.

### Cleared the evidence gate

| Signal | Model | Precision | Recall | F1 | n | Evidence |
|---|---|---:|---:|---:|---:|---|
| Transaction | LightGBM *(frozen, held-out)* | 0.955 | 1.000 | 0.977 | 1,394,845 | strong |
| Transaction | XGBoost *(frozen, held-out)* | 0.965 | 0.875 | 0.918 | 1,394,845 | strong |
| Behavioural | Autoencoder *(frozen, held-out)* | 0.870 | 0.826 | 0.847 | 1,394,845 | strong |
| Voice | Deepfake-audio-detection | 0.966 | 0.950 | 0.958 | 204 | limited |
| Document | rapidocr + QR cross-check | 0.938 | 1.000 | 0.968 | 680 | strong |
| Text | Phishing (TF-IDF + LogReg) | 0.882 | 0.875 | 0.879 | 800 | strong |
| Identity | FaceNet video-KYC | 1.000 | 1.000 | 1.000 | 12 | **provisional** |

Fused (XGBoost + LightGBM + Autoencoder, weighted by each model's real Stage-5 ROC-AUC): **P 0.969 · R 1.000 · F1 0.984** over 1,394,845 held-out rows.

### Did not clear it

| Signal | Model | Recall | Status |
|---|---|---:|---|
| Graph | GraphSAGE mule-network (round 5) | 0.075 | `experimental` |

The GNN is shown at its real value. Round 5 added genuine graph-topology, temporal/velocity and port-numbering features and moved recall from 0.004 to 0.075 — a real improvement to a signal that is still not good enough to act on. It is not hidden, not rounded up, and not quietly dropped from the fusion layer's provenance. **Mule-network detection currently rests on the sequence features in the tabular models, not on the GNN.**

---

## Two findings worth a judge's attention

**A threshold picked on validation data did not transfer.** `phishing_classifier`'s decision threshold, chosen with `best_f1_threshold()` against real difraud validation data, produced a **39% false-positive rate** when the same frozen detector was re-scored against our own generated evidence-gate set. Nothing about the model changed — only the distribution it was asked to decide on.

Recomputing that detector's scores per mutation combination showed why, and it
is sharper than "distribution shift": **the classifier is substantially an
urgency detector**. Every held-out combination carrying `urgency: high` is
caught 100% of the time — Hinglish included, which was the obvious suspect and
was wrong. The one combination carrying `urgency: low` scores a mean of 0.288,
*below the mean of the legitimate messages* (0.403). Low-urgency phishing
doesn't merely slip the threshold; it ranks as more innocuous than the average
real message, and the same cue is what makes an urgently-worded genuine payment
reminder a false positive. No threshold separates those two. The held-out split
found this precisely because `urgency` is one of its split dimensions — a
same-distribution validation set could not have, since difraud's phishing
corpus is overwhelmingly high-urgency.

The architectural response is in `docs/TECHNICAL_SPEC.md` §6: a detector's job is to output a *well-ranked continuous score*; the ALLOW / REVIEW / CHALLENGE / BLOCK decision is made one layer up, in fusion, where a miscalibrated signal gets corroborated or discounted by the others. No single detector's threshold is ever the final fraud decision. This is what lets an honestly-documented imperfect signal be a component rather than a liability.

**Detection rate alone is a misleading headline.** The UI reports outcomes as a confusion matrix, never as a single "attacks blocked" number, because `detected` in this codebase means *the prediction was correct* — a correctly-approved legitimate transaction counts as detected. Conflating that with "blocked" inflates the number by thousands. A run that never reached the evaluation stage displays "not measured", never `0.0%`.

---

## Repository map

```
backend/
  generate/        Red Team — one generator per family, plus the mutation engine
    artifact_generators/   audio, invoice images, scam scripts, message text
    generate_video_kyc_attacks.py  lookalike-impostor video/photo pairs
    synthetic_customers.py Customer Universe: reference voice, photo, trusted payees
    mutation_engine.py     targeted second-round attacks against the weakest family
  defend/          Blue Team
    train/                 XGBoost, LightGBM, Autoencoder (genuinely trained here)
    pretrained/            voice spoof, document consistency, video KYC, phishing
    fusion.py              per-signal scores -> one fusedRiskScore (0-100)
  evaluation/      the harness — the only place ground truth meets a prediction
    split_policy.py        which mutation combinations are train vs. held-out-only
    run_all_evaluations.py one entry point per modality
  orchestration/
    agent_runner.py        the closed loop as one run: generate -> score -> mutate
  api/main.py      FastAPI: run control, live status, stop, data hydration
  db/migrations/   Supabase schema, RLS, realtime, storage buckets

frontend/          React + Vite + shadcn/Tailwind
  features/warroom/        live run: per-stage progress, evidence playback, stop
  features/dashboard/      corpus-wide view
  services/api/            reads Supabase directly with the anon key

notebooks/fraudshield_colab_master.ipynb   GPU work: OCR, voice generation,
                                           video-KYC, GNN training (A–E sections)
docs/              spec, dataset provenance, every recorded evaluation result
```

---

## Running it

**Prerequisites:** Python 3.11+, Node 18+, a Supabase project.

```bash
git clone https://github.com/officialayush23/red_hat_vs_blue_hat_attack.git
cd red_hat_vs_blue_hat_attack

# 1. Database
#    Apply backend/db/migrations/*.sql to your Supabase project, in order.

# 2. Credentials — never committed; .env is gitignored
cp .env.example .env      # SUPABASE_URL, SUPABASE_ANON_KEY,
                          # SUPABASE_SERVICE_ROLE_KEY, HF_TOKEN.
                          # GEMINI_API_KEY is optional — see Principle 9.

# 3. Backend
pip install -r backend/requirements.txt
uvicorn backend.api.main:app --reload        # http://localhost:8000/health

# 4. Frontend
cd frontend && npm install && npm run dev    # http://localhost:5173
```

**To watch the closed loop run**, start an adversarial evaluation from the UI (or `POST /runs/start`) and open the war room. It streams per-stage progress, plays each artifact as it is scored, and can be stopped mid-run.

**GPU work** — OCR at scale, voice cloning, video-KYC, GNN training — runs from `notebooks/fraudshield_colab_master.ipynb` on Colab or Kaggle. Each section checkpoints its results back to Supabase before the runtime can be reclaimed, so a disconnect costs time, not evidence.

Some evaluation paths need their own interpreters (OCR and voice-generation dependency stacks conflict); `run_all_evaluations.py` routes those steps to the right venv automatically.

---

## Honest limitations

- **Video-KYC recall of 1.000 rests on 12 cases.** It is labelled `provisional` everywhere it appears and should be read as "the pipeline works end to end", not "this detector is validated".
- **The GNN does not work well enough to use.** See above.
- **Voice bonafide samples come from a small LibriSpeech sample**, not from the same recording conditions as the spoofs. Some of that 0.966 precision may be channel separability rather than spoof detection.
- **Document detection is inference over a pretrained OCR stack**, not a model we trained. Per Principle 6, using an existing validated model honestly is not a lesser claim than training a worse one — but it is a different claim, and it is stated as such.
- **Attack families are not equally deep.** Transaction-side families have hundreds of thousands of rows; voice has 357 cases. Simulation coverage and detection coverage are tracked separately and never merged into one accuracy number.

---

## Documentation

| Document | What it holds |
|---|---|
| [`docs/TECHNICAL_SPEC.md`](docs/TECHNICAL_SPEC.md) | The frozen build reference: 14 governing principles, attack taxonomy, fusion design, evaluation protocol |
| [`docs/EVALUATION_RESULTS.md`](docs/EVALUATION_RESULTS.md) | Every number this project has produced, appended as it was produced — including the ones that got worse |
| [`docs/DATASETS.md`](docs/DATASETS.md) | Provenance for every dataset, and the GNN's full round-by-round feature history |
| [`docs/AGENTIC_CONTRACT.md`](docs/AGENTIC_CONTRACT.md) | The mutation loop's data contract, and a standing section on what is *not* built yet |
| [`docs/FUTURE_INTEGRATIONS.md`](docs/FUTURE_INTEGRATIONS.md) | Deliberately deferred work, with the reasoning |

`EVALUATION_RESULTS.md` is append-only and machine-written at the point each run finishes. It contains superseded numbers, failed rounds, and results that contradict earlier ones. That is the point: it is the audit trail behind every claim above.
