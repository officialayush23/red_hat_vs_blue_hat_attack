# FraudShield — Frozen Technical Spec

**Target:** Mastercard Innovation Challenge 2026 (AI Defense Lab for Payment Security), hosted on Kaggle.
**Deadline:** Aug 31, 2026, 11:59 PM IST.
**Judged on:** diversity of attacks identified · fidelity of attacks in simulation · detection algorithm efficacy · novelty · real-world feasibility in live payments.
**Required submission:** (1) a complete, organized, documented, reproducible GitHub code repo covering identify/generate/defend, (2) a Solution Walkthrough as a `.docx`, (3) a working web-based prototype demonstrating the closed loop.

This document is the frozen build reference. It supersedes prior chat discussion where they conflict.

---

## 1. Governing principles

1. Mastercard's problem statement is the target — not the CuriousPARC rubric, not enterprise-architecture completeness for its own sake.
2. Red Team + Blue Team, as one closed loop, is the core product — not an agent framework, not a dashboard.
3. The LLM chooses attack *strategy*. Deterministic code generates the actual financial data. The LLM never writes a transaction row, an amount, a balance, or a timestamp.
4. No LLM-generated transaction rows, ever, under any circumstance — including "just for variety."
5. XGBoost, LightGBM, Autoencoder, and GNN are genuinely trained by us, on real data, with real evaluation.
6. Voice and document fraud detection use pretrained inference where a validated pretrained model exists — training a deepfake/OCR model from scratch is out of scope, and using an existing one honestly is not a lesser claim.
7. The adversarial test set is generated only after the Blue Team is frozen, using mutation parameter combinations excluded from training. This is what makes the "detects novel fraud" claim defensible rather than asserted.
8. Every generated attack produces a persistent, inspectable artifact (audio file, image pair, message text, or transaction sequence) — not just a derived score. This is direct evidence for "fidelity of attacks in simulation."
9. The system must fully function with the LLM strategist disabled — it degrades to a rule-based/random mutation selector, not a system failure. The LLM is an enhancement layer, never a single point of failure.
10. Every model in the system has an actual, recorded evaluation result before the Solution Walkthrough is written. No model ships without numbers.
11. **Evidence gate (added 2026-08-30).** No modality or model is promoted to a "validated" claim in the Blue Team without a real detector run against a real, frozen held-out evaluation set with recorded metrics. Anything short of that ships as "experimental" / research-tier and is labeled as such everywhere it appears -- model registry, dashboard, Solution Walkthrough. An attack family may exist in the Red Team's simulation library before its Blue Team detector clears this gate; simulation coverage and detection coverage are tracked and displayed separately, never conflated into one invented accuracy number.
12. **Orchestration is deterministic-tool-execution-plus-LLM-strategy, not a new agent framework (added 2026-08-30).** Multi-stage attacks ("identity impersonation -> account takeover -> fraudulent payment") are predefined composite scenarios built by chaining *existing* attack-family generators -- not a new generalized campaign-orchestration engine. The LLM strategist (Phase 4, Principle 9 still applies) may choose which existing primitives to chain and in what order; it does not gain new generative surface by being an "orchestrator."
13. **Attack labels are evaluation-only metadata, never a detector input (added 2026-08-30, formalizing a rule already followed in practice).** A `attack_family`, `is_fraud`/`ground_truth`, `campaign_id`, or any other Red-Team-authored label lives in the case record for the evaluation harness to read -- it must never reach a detector's input, whether that detector is a trained model (XGBoost/LightGBM/Autoencoder/GNN) or a pretrained-inference wrapper (voice spoof, document consistency, phishing text). A detector receives only what a real production system could observe at inference time: the artifact itself (audio file, image, message text), the transaction/event fields, and reference state from the Customer Universe (Section 4b-i) -- never the family it was generated from or whether it's fraud. Concretely: `DocumentConsistencyDetector.score()` and `VoiceSpoofDetector.score()` already take only a file path, nothing else -- confirmed by reading both files directly, neither has ever imported or referenced `attack_family`/`is_fraud`/`ground_truth`. This is what makes "detects novel fraud" a defensible claim rather than the detector being told the answer -- ground truth is compared against a prediction only inside the evaluation harness (Principle 11's evidence-gate runs, `evaluation/metrics.py`), after the detector has already produced its score blind to the label. Every new detector built from here on (#31 phishing, #33 GNN, #35 composite-scenario scoring, #36's live API) must preserve this boundary explicitly, not by accident of which fields happened to get passed in.
14. **Context fusion over independent per-signal scores, where the data supports it (added 2026-08-30).** A single event scored in isolation misses exactly the cases that matter most -- a mule-relay hop looks like an ordinary small transfer on its own; a synthetic KYC document looks fine without a reference to compare against. Section 6's risk fusion already combines per-signal scores into one `fusedRiskScore`; this principle extends that idea one layer earlier, into what each signal is computed *against*: identity signals compare an observed artifact (uploaded photo/voice/document) to that customer's own Customer-Universe reference state, not just to a generic bonafide/fraud threshold, wherever a `customer_id` is available (document_fraud and voice_scam already do this -- beneficiary-vs-trusted-list and cloned-vs-registered-voice, Section 4b-i); graph/mule-network signals reason over the transaction sequence and cross-account/cross-bank relationships (Section 4a), not a single transfer amount. This is scoring composition over existing signals, same as Section 4c's cross-modal identity fusion -- not a new detector family, and every component signal it fuses must independently clear Principle 11 before its contribution counts toward the fused score.

GNN is core scope, sequenced after the core tabular loop — the constraint on it is engineering integration complexity (correct graph construction, no train/test leakage, defensible labels), not GPU training time (confirmed: nothing in this spec needs more than ~1 hour of training compute). The same evidence-gate discipline in Principle 11 applies to it: it ships as the graph signal only once its held-out evaluation is real; the graph-derived-features-into-XGBoost fallback from Phase 1 stays available if it doesn't clear in time.

---

## 2. Repository structure

```
red_hat_vs_blue_hat_attack/
├── frontend/                        # existing React + shadcn dashboard, rebuilt against real API
├── backend/
│   ├── identify/
│   │   └── attack_taxonomy.md       # the two tables in Section 4, as source of truth
│   ├── generate/                    # RED TEAM
│   │   ├── templates/               # one parameterized template per attack family
│   │   ├── mutation_engine.py       # deterministic mutation logic, all dimensions
│   │   ├── llm_strategist.py        # optional: weakness -> strategy JSON -> mutation params
│   │   ├── validators.py            # statistical sanity checks on generated attacks
│   │   └── artifact_generators/
│   │       ├── transaction_gen.py   # PaySim/IEEE-CIS-seeded synthetic transactions
│   │       ├── ring_gen.py          # networkx synthetic mule/fraud-ring graphs
│   │       ├── voice_gen.py         # TTS scam-script audio generation
│   │       └── document_gen.py      # invoice + QR generation and tampering
│   ├── defend/                      # BLUE TEAM
│   │   ├── notebooks/               # one training notebook per trained model
│   │   ├── models/                  # exported model artifacts (xgboost.json, lightgbm.txt, autoencoder.pt, gnn.pt)
│   │   ├── features/                # feature engineering, shared between train and inference
│   │   ├── pretrained/              # thin wrappers around HF voice-spoof / OCR inference
│   │   └── inference/               # serving layer (see Section 7)
│   ├── evaluation/
│   │   ├── split_policy.py          # train-allowed vs held-out mutation combinations, per family
│   │   ├── run_adversarial_eval.py  # freeze -> generate held-out -> score -> metrics
│   │   └── metrics.py               # precision/recall/F1/ROC-AUC/PR-AUC, per family and overall
│   ├── api/                         # request handlers, matches contract in Section 7
│   └── db/                          # Supabase schema + migrations
├── docs/
│   ├── TECHNICAL_SPEC.md            # this file
│   ├── ATTACK_TAXONOMY.md
│   └── EVALUATION_RESULTS.md        # filled in once real numbers exist — feeds the .docx directly
└── README.md                        # setup + reproduction instructions (required by submission rules)
```

---

## 3. Datasets — verified

| Dataset | Role | Verification status |
|---|---|---|
| PaySim1 (Kaggle, `ealaxi/paysim1`) | Primary transaction training, 6.36M rows | Confirmed real, row count matches |
| IEEE-CIS Fraud Detection (Kaggle) | Secondary/card-fraud validation set | Confirmed real, already Mastercard-doc-referenced |
| Synthetic mule/fraud rings | Graph structure for GNN + graph-derived features | Self-generated via `networkx` — no external dataset dependency, full control over topology |
| `difraud/difraud` (Hugging Face) | Candidate source for phishing/text-fraud training data | Real, found via search — **contents/license not yet inspected, verify before hard dependency** |

Explicitly dropped: "SynSEPA," "Free Synthetic Fraud Rings," "FraudForge" — none resolved to a real, findable dataset under those names in either Kaggle or Hugging Face search. Do not reintroduce without independently re-verifying.

---

## 4. Attack taxonomy

Two separate tables, deliberately not collapsed into one. An attack *family* is what the Red Team generates. A *signal category* is what the Blue Team scores. One attack can and should light up multiple signal categories.

### 4a. Attack families → expected signals → training vs. held-out mutation split

| Attack family | Base scenario | Mutation dimensions | Expected signals | Training-allowed combinations | Held-out-only combinations |
|---|---|---|---|---|---|
| Transaction fraud | Card-testing / CNP fraud | amount, velocity, merchant category, time-of-day | transaction | low-amount+high-velocity; high-amount+low-velocity; standard merchant mismatch | mid-amount+moderate-velocity+new-merchant-category+off-hours (never combined in training) |
| Account takeover | Compromised account, new device | device, location, beneficiary change, velocity | transaction, behavioral, device | new-device+new-location; beneficiary-change+high-velocity | new-device+trusted-location+gradual-velocity-ramp (evasive combination) |
| Synthetic identity | New account, thin history | account age, device history, behavior pattern, relationship count | behavioral, device, graph | low-age+limited-history+normal-then-abnormal pattern | low-age+limited-history+gradual-ramp+merchant-relationship-building (slow-burn evasion) |
| Mule network | Coordinated multi-hop transfer, single-bank or cross-bank relay | hop count, shared device, timing gaps, cash-out, cross-bank hop | graph, transaction | 2-3 hops, short gaps, shared device present, same-bank hops | 4+ hops, long/irregular gaps, no shared device, distributed beneficiaries, hops crossing 2+ banks before cash-out (the evasive ring shape -- individual hops look like ordinary small transfers; only the graph across banks reveals the ring) |
| Phishing / social engineering | Scam SMS/email/WhatsApp message | urgency level, impersonation target, language | text | standard urgency + common impersonation targets | novel impersonation target + low-urgency wording (designed to read as legitimate) |
| Voice scam | Cloned/synthetic voice, scam script | script type, urgency, voice characteristics | voice | standard bank-manager / KYC scripts | novel script framing (e.g. "family emergency" instead of "KYC") |
| QR / document fraud | Tampered invoice or QR payload | amount, beneficiary, QR payload, invoice number | document | single-field tampering | multi-field simultaneous tampering (amount + beneficiary + QR together) |

Each attack case, in storage, carries an explicit `splitPortion: "train" | "held_out"` field derived from which combination bucket it was generated from — this is what makes the held-out claim auditable rather than asserted.

### 4b-i. Synthetic Customer Vault

A `synthetic_customers` record is the anchor identity for the research-tier families in 4c and for framing account-takeover chains as "impersonate customer X" rather than isolated cases: a synthetic (never real) KYC-style document reference, reference photo, voice sample, video-KYC baseline, device history, and financial/relationship history, all references to Storage artifacts plus metadata -- no real Aadhaar/PII data, ever (Principle 8's persistent-artifact requirement applies here too). `attack_cases` may optionally reference a `customer_id`; most transaction/behavioral families don't need one, the identity-impersonation families do.

**behavior_baseline (added 2026-08-30):** each customer's `metadata.behavior_baseline` carries normal-and-occasional ranges for amount, country, channel, and login hour, plus regular-beneficiary/transfer-frequency counts (`generate/synthetic_customers.py`). This is deliberately a summary-statistic reference state, not a fabricated transaction log or account graph -- `mule_network`'s actual topology is built where it belongs, in that family's own generator (Task #33). The "occasional" ranges exist specifically so a held-out evaluation isn't trivially easy: a customer who never transacts above a fixed ceiling would make ANY deviation read as fraud, which teaches "weird = fraud" rather than actual fraud signal -- real customers travel, use a new device occasionally, or transact at 2am sometimes, and an attack has to hide inside that same plausible envelope. Primary consumers are `mule_network` and `account_takeover` -- both are fundamentally "is this typical for this customer" problems. `phishing_scam` deliberately does NOT get behavior_baseline wired in as a rearchitecture -- it's a content-manipulation problem, not a behavioral-deviation one; the one exception is a light sender/channel-novelty feature, folded into Task #33's work since it's the same schema field, not spun into its own workstream.

### 4c. Research-tier attack families (evidence-gated, added 2026-08-30)

These extend the taxonomy toward the multimodal identity-impersonation surface Mastercard's brief explicitly names (synthetic identities, deepfake KYC, GenAI-enabled scams). They enter the Red Team's simulation library immediately under Principle 8. Each enters the Blue Team's *validated* signal set only after clearing Principle 11's evidence gate -- until then it's simulation-only and labeled that way.

| Attack family | Base scenario | Expected signal | Candidate detector | Status |
|---|---|---|---|---|
| Video KYC impersonation | Synthetic/manipulated video of a synthetic customer performing remote identity verification | identity (video) | Reference-image + temporal-identity-consistency approach (per eKYC-DF-style research), fallback: a pretrained KYC-deepfake checkpoint, evaluated ourselves on our own generated set -- never take a model card's headline accuracy as our number | Research spike (Task: video-KYC evidence gate) |
| KYC photo/face impersonation | A synthetic customer's reference photo replaced/manipulated via generative image techniques | identity (image) | Face-embedding similarity vs. the customer's registered reference photo, plus a manipulation-artifact check | Research spike |
| Card testing / reconnaissance | Many small authorization attempts to validate live cards/accounts before a larger attack | transaction | Reuses the already-trained XGBoost/LightGBM transaction models -- this is a mutation pattern *within* the existing transaction_fraud family, not a new detector | Core-eligible immediately, no new model required |
| AI-generated fake merchant / payment destination | AI-generated storefront or manipulated merchant identity redirecting a legitimate-looking payment | transaction, document | Reuses the QR/document consistency detector plus the transaction anomaly signal | Core-eligible immediately, no new model required |

Cross-modal identity fusion (correlating photo + voice + video + document signals for one synthetic customer into an identity-risk score) is a *scoring composition* over the signals above -- not a new model -- and ships once at least two of its component signals are individually validated.

Agentic payment/instruction abuse is explicitly out-of-scope for this submission -- noted in the Solution Walkthrough as a forward-looking direction, not built, not claimed.

### 4b. Signal categories (the fixed scoring contract)

`transaction`, `behavioral`, `device`, `graph`, `text`, `voice`, `document` — seven core categories, each backed by one or more of the trained/pretrained models in Section 5, fused into one risk score in Section 6. An eighth category, `identity` (video/photo/cross-modal, Section 4c), is additive and evidence-gated per Principle 11 -- it only enters the fusion score once at least one of its component detectors is validated, and never contributes an invented number before that.

---

## 5. Models

| Model | Trained by us | Purpose | Training data | Expected training time | Sequencing |
|---|---|---|---|---|---|
| XGBoost | Yes | Primary tabular classifier — transaction + account-takeover signals | PaySim + IEEE-CIS, engineered features (~30-50, trimmed from the original 135-feature spec down to what actually matters: velocity, amount deviation, time-of-day, device match, account age, merchant trust) | Minutes | Phase 1 (core loop) |
| LightGBM | Yes | Same feature space, different learner — ensemble diversity, not redundancy | Same as XGBoost | Minutes | Phase 1 |
| Autoencoder | Yes | Unknown/zero-day fraud — trained only on legitimate transactions, reconstruction error as anomaly score | PaySim/IEEE-CIS legitimate transactions only | Minutes | Phase 1 |
| GNN (GraphSAGE or GAT, PyTorch Geometric) | Yes | Mule-network / fraud-ring detection over the self-generated ring graphs | `networkx`-generated synthetic rings | Well under an hour on a modest graph | Phase 3 — after core loop works end-to-end |
| Voice spoof/deepfake detector | No — pretrained inference | Score synthetic scam-call audio for spoof probability | N/A (inference only) -- evaluated on our own generated bonafide/spoof set | Zero | **Selected 2026-08-30**: `garystafford/wav2vec2-deepfake-voice-detector` (Apache 2.0, plain `transformers`, XLS-R-300M backbone, trained against real TTS platforms). Rejected the SOTA paper-reproduction candidate (XLS-R-SLS, ACM MM 2024) -- needs fairseq plus a separate ~1.2GB SSL checkpoint and custom model code, real integration risk for a claim we would still have to re-verify on our own data anyway. See `backend/defend/pretrained/voice_spoof_detector.py`. |
| OCR / document consistency (PaddleOCR) | No — pretrained inference | Extract invoice fields, cross-check against QR payload | N/A (inference only) | Zero | Phase 2 |
| Text/phishing classifier | Light training or lightweight pretrained | Score phishing/scam message text | `difraud/difraud` (MIT license, confirmed 2026-08-30 -- 95,854 samples across 7 domains; phishing_email (15,272) and sms_scam (6,574) subsets are the ones we use, both directly on-topic for this family) | Minutes | Phase 2 |
| Video-KYC identity-consistency detector | No — pretrained, self-evaluated | Score synthetic/manipulated KYC video against a synthetic customer's registered reference photo | N/A (inference only) -- evaluated on our own generated genuine-vs-manipulated set | Research spike (hours, not days) | Research spike -- promoted to this table's "core, validated" status only if it clears Principle 11's evidence gate; otherwise stays research-tier/experimental in `model_registry` and the dashboard |
| Face/photo manipulation detector | No — pretrained, self-evaluated | Score a KYC photo's authenticity vs. the customer's reference photo | N/A (inference only) | Research spike | Same evidence-gate treatment as above |

No component in this table requires anywhere near a day of training. The binding constraint throughout is integration and evaluation-harness correctness, not compute. The two research-spike rows are explicitly allowed to fail the evidence gate and ship as experimental -- that is a correct, honest outcome under Principle 11, not a shortfall.

**Tabular preprocessing pipeline (added 2026-08-30).** XGBoost/LightGBM share one saved, versioned preprocessor (`backend/defend/train/preprocessor.py`'s `TabularPreprocessor`, fit by `backend/defend/train/fit_preprocessor.py` from the same source files `dataset.load_training_pool()` already combines) instead of each caller re-deriving categorical handling ad hoc. This exists because of two real bugs hit building `evaluation/run_adversarial_eval.py`: an all-NaN categorical column (`card_type`/`card_network` -- the synthetic generator never models these IEEE-CIS-only fields) produced an empty pandas category set and crashed XGBoost's predict path outright, and XGBoost separately hard-errors on any categorical value it never saw during training -- which a held-out-only combination (Section 4a, by design) always is. The preprocessor masks any out-of-vocabulary categorical value to missing before scoring, which is the only way XGBoost can score these rows at all; a genuinely novel categorical *value* is therefore evaluated as a missing field for that one feature, not as the value itself -- a real, stated limitation of tree-model categorical handling, not a shortcut. Fitting this preprocessor from the same deterministic source files does not change or require retraining the already-frozen XGBoost/LightGBM models. The Autoencoder is unaffected -- it already carries its own self-contained preprocessing (`train_autoencoder.py`'s `fit_preprocessor()`/`transform()`, saved inside `autoencoder.pt`), so it is not duplicated here. This pipeline is a prerequisite for Task #36's live API (some deterministic raw-request -> model-input path is required for it to exist at all) and is explicitly *not* the mechanism by which the system adapts to new attack patterns -- that is Section 8's adversarial mutation loop (`weakness_log`, Task #35's LLM strategist), a different mechanism operating on attack combinations rather than on data schema. This pipeline's job is narrower: consistent, crash-free scoring, not higher accuracy -- accuracy is bounded by model/features/data, and building this did not and was never intended to change any reported metric.

---

## 6. Risk fusion & decision engine

Each transaction/case produces per-signal scores from the relevant models above, fused into one `fusedRiskScore` (0-100). Decision bands (our own design choice, not a Mastercard requirement):

| Score | Decision |
|---|---|
| 0-30 | Approve |
| 31-60 | Review |
| 61-80 | Challenge |
| 81-100 | Block |

Fusion weighting starts from equal-ish weighting per active signal and gets tuned once real precision/recall numbers exist in Phase 1 — do not hand-tune weights before there's a held-out evaluation to tune against.

**Threshold selection is delegated to this layer, not baked into individual detectors (added 2026-08-30, real finding from phishing_classifier).** A per-model decision threshold picked during Stage 5 training (e.g. `best_f1_threshold()` against a validation split) is a reference operating point on *that* model's own training distribution -- it is not assumed to be the right allow/review/block cutoff once the signal is deployed. Concrete evidence: phishing_classifier's threshold, picked via `best_f1_threshold()` on real difraud/difraud validation data, produced a 39% false-positive rate when the same detector was re-scored against our own generated evidence-gate set (evaluation/eval_phishing_classifier.py) -- the threshold didn't transfer. Each detector's job is to output a well-ranked continuous risk score (its ROC-AUC/PR-AUC is what's load-bearing); the ALLOW/REVIEW/CHALLENGE/BLOCK decision happens once per-signal scores are combined with Customer Universe behavioral context (Section 4b-i, Principle 14) in this fusion layer -- a weak or miscalibrated individual signal gets corroborated or discounted by the others rather than acting alone. This is what makes an imperfect per-family detector (documented honestly, per Principle 11) a legitimate system component rather than a liability: no single detector's threshold is ever the final fraud decision.

---

## 7. API contract

Endpoints (adjust freely during implementation — this is a working contract, not a locked interface):

- `POST /api/generate-attack` — Red Team generates one attack scenario (family, mutation params, optionally guided by a strategy from `/api/strategize`)
- `POST /api/evaluate` — runs a generated case through the frozen Blue Team, returns signals/score/decision/evidence
- `POST /api/run-adversarial-batch` — generates and evaluates N cases across families in one run, returns aggregate + per-case results
- `POST /api/strategize` — LLM strategist: given a weakness summary, returns structured JSON (`attack_family`, `objective`, `mutations`, `reason`) that the mutation engine executes; this endpoint is optional at runtime — its absence must not break the system (Principle 9)
- `GET /api/runs`, `GET /api/runs/:id`, `GET /api/cases/:id`
- `GET /api/dashboard/stats`

Evaluation case shape (the artifact requirement lives in `artifacts`, populated per attack family — most fields null for any given case):

```json
{
  "id": "case_0001",
  "attackFamily": "voice_scam",
  "mutationParams": { "script": "kyc_verification", "urgency": "high" },
  "splitPortion": "held_out",
  "signalsExpected": ["voice"],
  "modelSignals": [
    { "model": "wav2vec2_spoof", "category": "voice", "score": 0.91, "triggered": true }
  ],
  "fusedRiskScore": 88,
  "decision": "block",
  "detected": true,
  "actualLabel": "fraud",
  "evidence": [{ "signal": "spoof_probability", "contribution": 0.91 }],
  "artifacts": {
    "audioUrl": "https://.../case_0001.mp3",
    "imageBeforeUrl": null,
    "imageAfterUrl": null,
    "qrPayload": null,
    "messageText": "This is your bank calling regarding urgent KYC verification...",
    "transactionSequence": null
  },
  "generatedBy": "llm_strategy_v3",
  "createdAt": "2026-08-30T14:22:00Z"
}
```

Stack correction (2026-08-30): frontend is Vite + React (not Next.js), backend is a standalone FastAPI app served via uvicorn (not Node/serverless functions) -- `backend/api/` per Section 2's repo structure. Deployment target for the FastAPI app is not yet decided (a small always-on host -- Render/Railway/Fly -- or simply local `uvicorn` for the judging demo); this does not block Phase 2-5 work and gets decided when Phase 5's real API is wired. Voice-spoof / video-KYC / photo inference all run as normal in-process (or same-host) model calls from FastAPI -- no serverless packaging constraint exists here since there's no serverless target, so weight size and cold starts are non-issues; the only real constraint is total VRAM if multiple models are loaded on the same GPU as training (RTX 3050 6GB) -- load pretrained inference models on CPU where latency allows, reserve GPU for anything that benefits materially (video generation/inference).

---

## 8. Adversarial evaluation protocol

1. Generate training-portion attacks only, using the training-allowed combinations in Section 4a, plus legitimate baseline transactions from PaySim/IEEE-CIS.
2. Train XGBoost, LightGBM, Autoencoder (and later GNN) on that data. Freeze the models — no further training after this point.
3. Generate the held-out adversarial set using only the held-out-only combinations in Section 4a — combinations the frozen models never saw during training.
4. Score the held-out set. Record precision, recall, F1, ROC-AUC, PR-AUC, false positive rate — overall and broken out per attack family.
5. Identify the weakest family/combination (lowest recall). This is the "weakness" fed to the LLM strategist (or, with the LLM disabled, to a rule that just proposes the next unexplored parameter direction).
6. Generate a second round of attacks targeting that weakness specifically, still drawn from the held-out combination space, not retrained-on. Re-evaluate. This before/after delta is the demo's central evidence.
7. Every number in this protocol gets written down in `docs/EVALUATION_RESULTS.md` as it's produced — that file is the direct source for the "detection and mitigation model, with efficacy results" section of the required `.docx`.

---

## 9. Frontend / UI requirements

- Visual, modern, animated dashboard — extend the existing shadcn/Tailwind build rather than rebuild from scratch; it already reads well in both themes.
- The Red Team <-> Blue Team attack simulation canvas (already built) is the centerpiece and gets upgraded to be expandable (fullscreen/modal), zoomable and pannable (not just a fixed 300px strip), and driven by live data from real evaluation runs rather than mock data.
- Every case, on click or hover, expands into an evidence panel matching its `artifacts` payload: an audio player for voice, a before/after image toggle for documents, the raw message text for phishing, a transaction-sequence table for the tabular families.
- "Live changes" — evaluation runs push updates via Supabase Realtime as they progress, so the canvas animates attacks arriving during an actual run rather than only replaying finished history.
- Frontend category enum, mock data, and any component still reading from `mockStore.js` get remodeled to match the real API contract in Section 7 once the backend exists — this is expected rework, not a bug.

---

## 10. Build sequence

**Phase 1 — Core loop, real data, real numbers. DONE.** Attack templates + mutation engine for transaction, account-takeover, synthetic-identity, mule-network families (mule via self-generated rings, graph-derived features into XGBoost/LightGBM rather than a trained GNN yet). Trained XGBoost, LightGBM, Autoencoder, real validation metrics recorded. Adversarial evaluation harness (Section 8) still pending Phase 1.5/2 backfill into Supabase before it can run against live data.

**Phase 1.5 — Supabase foundation (added 2026-08-30, pulled forward).** Schema for `synthetic_customers`, `attack_cases`, `evaluation_runs`/`evaluation_results`, `model_registry` (the evidence cards Principle 11 requires), `attack_campaigns`/`campaign_runs`, `weakness_log`. RLS on (service-role writes, public read -- this is synthetic data by design, Principle 8). Realtime enabled on `evaluation_results` and `campaign_runs` for Section 9's live-canvas requirement. Storage buckets for attack artifacts and synthetic-customer identity assets. Stage 4's already-generated attack cases backfilled in, so the DB isn't empty once the API exists. Migrations committed under `backend/db/migrations/` -- built once, evolved with the codebase from here on, not thrown away.

**Phase 2 — Multimodal + artifacts.** Voice scam generation (TTS) + pretrained spoof detection. Document/QR generation + tampering (documents framed as synthetic KYC-style where relevant, never real Aadhaar) + PaddleOCR consistency check. Phishing text generation + classifier. Artifact persistence to Supabase Storage (Phase 1.5's buckets). Evidence viewer in the frontend. Card-testing and fake-merchant families (Section 4c) ship alongside this phase since they need no new model.

**Phase 2.5 — Research spikes: video-KYC + photo/face impersonation (Section 4c, evidence-gated).** Generate a small synthetic-customer genuine-vs-manipulated photo/video set. Evaluate the reference-image + temporal-consistency approach and a pretrained KYC-deepfake checkpoint against it ourselves. Promote to validated `identity` signal only if the evidence gate (Principle 11) clears; ships as research-tier/experimental in the model registry and dashboard either way -- both outcomes are honest and reportable.

**Phase 3 — GNN.** Real GraphSAGE/GAT training on the synthetic ring graphs, replacing (or supplementing) the graph-derived-features-into-XGBoost approach from Phase 1. Same evidence-gate discipline as everything else.

**Phase 4 — LLM strategist + composite scenarios.** Wire `/api/strategize`, confirm the system still fully functions with it disabled (Principle 9). Build a handful of predefined composite scenarios chaining existing attack-family primitives (Principle 12) -- e.g. synthetic-identity -> account-takeover -> transaction fraud, or voice-impersonation -> beneficiary-change -> payment -- as the "attack chain" demonstration, without a new orchestration engine.

**Phase 5 — Documentation and polish.** Real API wired to Supabase (Section 7), frontend rewired off `mockStore.js` to live data (Section 9), model-registry-driven "validated vs. experimental" coverage display instead of any invented accuracy number. Write `docs/EVALUATION_RESULTS.md` from real numbers, then the `.docx` Solution Walkthrough from that. Dashboard animation/zoom/pan polish. README for reproducibility.

Each phase should leave a working, demoable state — Phase 1 alone is already a legitimate, honest submission if time runs out; everything after is additive, not load-bearing. Phase 2.5's research spikes are explicitly allowed to end in "experimental, not validated" -- that is still forward progress under Principle 11, never a blocker on the phases after it.
