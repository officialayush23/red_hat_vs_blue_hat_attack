# Dataset provenance -- what every model actually trained/evaluated on

Written 2026-08-30 in response to an explicit ask: show, per model in
`model_registry`, exactly what real data it was built and evaluated
against. Every line below is sourced from the actual training/eval script
that produced the frozen model, not asserted from memory -- see the "Verified
in" column.

| Model | Trained on (real data) | Fraud/attack examples | Held-out evaluation | Verified in |
|---|---|---|---|---|
| `xgboost`, `lightgbm`, `autoencoder` | PaySim + IEEE-CIS (Kaggle, real labeled transaction fraud) | Real fraud rows from both datasets, plus our own generated attack cases (`train` split only) | Our own generated attack cases (`held_out` split, never seen in training) across `transaction_fraud`/`account_takeover`/`synthetic_identity`/`mule_network` | `defend/train/dataset.py`, `evaluation/run_adversarial_eval.py` |
| `fusion` | N/A (combines the three above) | N/A | Same held-out set as above, all three signals fused | `defend/fusion.py`, `evaluation/eval_fusion.py` |
| `voice_spoof_detector` | Pretrained spoof detector (not trained by us) | N/A | Bonafide: `hf-internal-testing/librispeech_asr_dummy` (HuggingFace, real human speech, ~40-clip sample -- small-N caveat noted in the script itself). Spoof: our own generated voice attacks (Chatterbox TTS) | `evaluation/librispeech_bonafide.py`, `evaluation/eval_voice_spoof.py` |
| `document_consistency_detector` | Pretrained consistency detector (not trained by us) | N/A | Bonafide + fraud: both self-generated (`document_gen.py`) -- no external real-document dataset used here | `evaluation/eval_document_consistency.py` |
| `phishing_classifier` | `difraud/difraud` (HuggingFace, real labeled phishing/SMS text, MIT license) -- phishing + sms domains, train split | Real labeled phishing text from difraud | difraud's own validation split, plus a real evidence-gate re-check against our own generated phishing attacks (novel impersonation targets + Hinglish code-mixed text, both absent from difraud) | `defend/train/train_phishing_classifier.py`, `evaluation/eval_phishing_classifier.py` |
| `gnn` (mule-network graph model, Task #33 -- in progress) | **IBM Transactions for Anti-Money Laundering (AML)**, `ealtman2019/ibm-transactions-for-anti-money-laundering-aml` (Kaggle, HI-Small variant), a real peer-reviewed synthetic AML benchmark (IBM Research, NeurIPS 2023) with 8 labeled laundering typologies including fan-out/scatter-gather -- the same topology our own `mule_network` family models | IBM AML's labeled illicit subgraphs | Our own `ring_gen`-generated `mule_network` cases (`held_out` split, real graph structure, never seen in training) | `notebooks/train_gnn_mule_network.ipynb` (Colab), `evaluation/eval_gnn.py` |

## Why two different data sources per model, not one

Every detector here follows the same discipline: train on the largest,
most realistic REAL labeled data available for its modality (Kaggle
fraud datasets, HuggingFace speech/text corpora), then evaluate on our
own held-out generated attacks -- never trained on -- so the reported
recall reflects generalization to genuinely novel fraud patterns, not
memorization of the training distribution. The GNN follows this exact
same pattern: IBM AML for training (real, large-scale, purpose-built
for graph-based laundering detection), our own `ring_gen` held-out
rings for evaluation.

## What "adaptive" changes, and what it doesn't (Section 8)

None of the models above are retrained by the Section 8 adaptive
mutation loop (`evaluation/adaptive_weakness_round.py`), including the
GNN once it exists. Every model in this table is a **frozen artifact**,
trained once (locally for the pretrained/text models, or on Colab for
the GNN) and committed to the repo. "Adapt" means: identify the weakest
signal from a real held-out evaluation, generate a genuinely new,
harder combination of the SAME attack family the frozen model has
never seen, re-score it with the SAME frozen weights, and record a real
before/after recall delta. The model's parameters never change during
this loop -- only the test data does. This is a deliberate design choice
(Principle 9 / `docs/AGENTIC_CONTRACT.md`): it keeps the adaptive loop
fast, deterministic, and auditable (no risk of a bad round silently
degrading a model), at the cost of not letting the system "learn" from
what it discovers -- that gap is real and worth stating plainly rather
than implying otherwise.

## GNN feature schema history -- round 1/2/3 (Task #33)

The GNN's feature engineering went through three real, evidence-driven
iterations, each triggered by an actual Colab run's numbers, not
speculation:

- **Round 1**: edge features included a payment-format one-hot + a
  currency-match flag (real IBM AML columns). `ring_gen.py`'s own
  mule_network cases have no such concept, so cross-domain scoring
  hardcoded `payment_format="Cheque"` for every synthetic edge. Result:
  `mule_network` held-out recall 0/400, near-constant scores -- the
  hardcoded value was injecting whatever laundering-risk association the
  model learned for "Cheque" into every case, regardless of topology.
- **Round 2**: replaced the hardcoded value with a training-data
  prevalence-weighted average one-hot (marginalizing over the real
  distribution instead of guessing one category), plus a proper
  validation-based training regime (time-based train/val/test split,
  early stopping, best-checkpoint restoration) and fixed a real train/test
  leakage bug (node-aggregate features and the final eval had been
  computed over the full edge set, including val/test edges). Result:
  IBM AML PR-AUC barely moved (0.0018 -> 0.0028, still ~2x the 0.00123
  base rate); `mule_network` recall was still 0/400, with scores still
  collapsed into a near-constant band (0.5418-0.5431) -- because every
  synthetic edge still carried the *same* marginalized-prior payment
  format/currency values, so those dimensions still contributed no real
  per-case variation, and the training regime fix alone couldn't fix a
  feature-schema problem.
- **Round 3** (current): dropped payment-format and currency features
  entirely and rebuilt the schema around features that are REAL and
  NATIVELY PRESENT in both domains -- node-level fan-out/fan-in breadth
  (distinct counterparty counts) and a pass-through ratio
  (log(in-amount) - log(out-amount), a real mule signature: money relayed
  straight through nets near zero), plus edge-level cyclic hour-of-day and
  transaction velocity (time since this account's own previous send, and
  its running send-count so far) -- all derived from IBM AML's real
  `Timestamp` column and matched 1:1 against `ring_gen.py`'s own real
  `hour_of_day` / `time_since_prev_txn_same_entity` /
  `entity_txn_count_so_far` fields (verified field-for-field against real
  generated case files, including the shared "-1.0 = no prior transaction"
  sentinel convention). Training also switched from full-batch gradient
  descent with a ~1035x pos_weight (round 1/2 -- the val PR-AUC curve
  showed classic overfitting under this regime) to balanced mini-batch
  sampling with dropout and weight decay. Whether this actually produces a
  materially better `mule_network` recall is an empirical question for the
  next real Colab run -- these are the concrete, evidence-driven fixes for
  the two problems the round-2 run's own numbers pointed to, not a
  guarantee.

**What was deliberately left out, and why.** A materially richer
behavioral feature set -- account age, geographic/country deviation,
usual payment channel, customer-level KYC or demographic baselines -- was
considered and rejected for this model, not overlooked. Neither IBM AML
(a pure transaction ledger: bank, account, amount, currency, payment
format, timestamp -- no customer profile fields at all) nor `ring_gen.py`
(a topology generator with no customer concept) contains that data. Adding
those fields would mean fabricating them for one or both domains -- the
exact mistake round 1/2 made with payment-format/currency, at larger
scale. If genuine customer/KYC data becomes available, revisit this; until
then, the model only uses what the real data actually contains.

## Round 4 (Task #33 cont'd): grounding the GNN in published research

After round 3 was actually run on Colab, the real numbers were *worse* on
IBM AML than round 2 (ROC-AUC 0.5669 vs round 2's 0.6318; PR-AUC 0.0029;
precision 0.0096; recall 0.0211), and `mule_network` held-out recall was
still 0/400 at the threshold borrowed from IBM AML -- though
`percentile_vs_ibm_aml_test_scores` was 0.9561 (95.6th percentile),
meaning the model was still ranking real mule cases far above the typical
IBM AML transaction even though the specific threshold missed them. This
prompted checking actual published research on this exact dataset rather
than continuing to guess at architecture changes.

**What was found** (both papers fetched and read directly, not recalled
from memory):

- Altman, Egressy et al., *"Realistic Synthetic Financial Transactions for
  Anti-Money Laundering Models"* (NeurIPS 2023 Datasets & Benchmarks,
  arXiv:2306.16424) -- the actual paper defining the IBM AML/HI-Small
  dataset this project uses. Real Table 2 minority-class F1 numbers on
  HI-Small: GIN 28.70%, GIN+edge-updates 47.73%, PNA 56.77%, and
  **graph-feature-preprocessing + XGBoost (GFP+XGBoost) 63.23%** --
  beating every GNN baseline the paper tested, on this exact dataset.
- Egressy et al., *"Provably Powerful Graph Neural Networks for Directed
  Multigraphs"* (AAAI 2024, arXiv:2306.11586) -- reports up to +30%
  minority-class F1 from two specific, concrete techniques: **reverse
  message passing** (separate aggregation functions for a node's incoming
  vs. outgoing neighbors, concatenated rather than merged into one
  aggregator) and **port numbering** (a timestamp-ordered local index for
  each account among the transactions it sends and receives, attached as
  an edge feature).
- *"Detection, Attribution, Narration: An End-to-End Pipeline for
  Explainable Money Mule Identification"* (arXiv:2607.17586, July 2026, a
  real production system) -- uses LightGBM, not a GNN, on 280 engineered
  features (transaction/behavioral/network-topology/temporal), reporting
  real production numbers: precision 0.909, recall 0.816, alert yield
  improving 61% -> 89% after adding a SHAP-based explainability layer.
  Independently confirms the tree-model-plus-rich-features conclusion from
  a different, more recent, production (not benchmark) source.

**Decision (user chose "do both" over either alone):**

1. **GNN round 4**: adopted reverse message passing and port numbering
   from the AAAI 2024 paper. `DirectionalSAGELayer` now maintains separate
   `SAGEConv` aggregators for a node's predecessors (`edge_index` as-is)
   and successors (`edge_index` reversed), concatenating the two halves
   instead of merging into one aggregator. Edge features grew from 6 to 7
   dims with the addition of `out_port`/`in_port` (log1p-transformed,
   timestamp-ordered rank of each account among its own sent/received
   transactions -- IBM AML's real per-account send/receive order via
   `Timestamp`; `ring_gen.py` cases get the same rank computed from the
   case's own real chronological edge order). `NEG_PER_POS` raised 10->20,
   `PATIENCE` raised 15->25 (round 3 early-stopped at epoch 16, barely
   exploring). Cell 11's eval output now prints the published GIN/PNA/GFP+
   XGBoost baselines alongside the real run's own F1, so every future run
   is read against the actual literature, not a vibe. Deployed and
   verified (`ast.parse`, `nbformat.validate()`, a standalone numpy smoke
   test of the score_case feature-construction logic against real held-out
   case files) but **not yet re-run on Colab** as of this entry --
   `backend/evaluation/eval_gnn.py` was rewritten to match (architecture,
   `in_port`/`out_port`, reversed edge index) but is likewise unverified
   against a real round-4 `gnn.pt` until that run happens.
2. **Graph-feature-engineered XGBoost/LightGBM** (implemented and verified
   this entry -- see below): the published finding that GFP+XGBoost beats
   every tested GNN on this exact task is a real result on IBM AML's own
   HI-Small benchmark, and this project's own Phase 1 tabular pipeline was
   already positioned for it (`build_features.py`'s original docstring:
   *"Graph-derived features... get added once Stage 4... exists"*).

On the separate question of whether frozen models should be replaced with
real periodic retraining (arXiv:2607.17586 mentions this only vaguely, as
"periodic retraining on confirmed dispositions") -- the user explicitly
chose to **keep frozen, deterministic models** (Principle 9 unchanged).
The adaptive loop (Section 8, above) still only generates harder test
data against the same frozen weights; it does not retrain.

## Which attack families get real graph features, and why

Before writing any graph-feature code, checked whether any of the other
three generated Phase 1 families (`transaction_fraud`, `account_takeover`,
`synthetic_identity`) have a real multi-account graph structure worth
using, since `artifact_generators/transaction_gen.py` lists `"graph"` in
`synthetic_identity`'s `signals_expected`. Reading
`_generate_synthetic_identity()` directly confirms it is a single-entity
transaction sequence (`_build_sequence`, the same helper `transaction_fraud`
and `account_takeover` use) plus three scalar `extra_fields`
(`account_age_days`, `device_history_count`, `relationship_count` -- a
random integer count, not an actual graph of relationships). The `"graph"`
label in `_SIGNALS_EXPECTED` is a conceptual signal-category tag for the
mutation/detection framework, not a real generated graph payload. Only
`ring_gen.py` (`mule_network`) builds an actual `networkx.DiGraph` with
real nodes and edges. So graph-topology features are computed for real
PaySim rows and `mule_network` rows only; the other three generated
families, and IEEE-CIS, get NaN -- consistent with this codebase's
existing "never fabricate, leave null when the row's source has no real
signal" convention (already used for e.g. IEEE-CIS-only vs.
PaySim-only columns).

## Graph-topology features added to the tabular (XGBoost/LightGBM) pipeline

Seven new columns, computed identically (same formulas, same names) from
two different real graphs, so PaySim rows and generated `mule_network`
rows share one schema: `graph_src_out_degree`,
`graph_src_unique_out_counterparties`, `graph_src_pass_through_ratio`,
`graph_dst_in_degree`, `graph_dst_unique_in_counterparties`,
`graph_dst_pass_through_ratio`, `graph_in_port`.

- `pass_through_ratio(account)` = `min(total_in_amount, total_out_amount) /
  max(total_in_amount, total_out_amount)` when the account has both
  inbound and outbound transactions, else 0.0 -- our own derived ratio
  (not an asserted external fact), close to 1.0 for a classic
  layering/mule account and 0.0 for a pure source or sink. Same formula
  validated for the round-3/4 GNN's node features, reused here for
  consistency across the two model families.
- `graph_src_*`/`graph_dst_*`/`graph_in_port` for PaySim are computed from
  its own real `nameOrig`/`nameDest` columns
  (`build_features.py::_graph_topology_features`) -- account identifiers
  that were already being loaded for velocity but never used to build
  actual graph structure until now. Computed via `groupby`/`.map()` on
  account id, never a full-frame sort (same memory discipline as
  `_entity_velocity`). `graph_in_port` reuses `_entity_velocity`'s
  cumulative-count logic with `nameDest` as the "entity" -- the tabular
  equivalent of the GNN's `in_port`.
- For `mule_network` cases, the same seven columns are computed per-row
  from that case's own real `graph["edges"]`
  (`inject_attacks.py::_graph_features_for_case`), index-aligned 1:1 with
  `transaction_sequence` (verified: `ring_gen.py` builds both in the same
  loop, same order). Every other generated family gets an all-`None` row
  per transaction (no `"graph"` key on the case at all -- never fabricated).
- IEEE-CIS gets `np.nan` for all seven (no destination-account concept in
  card-not-present transactions).
- `dataset.py`'s `NUMERIC_FEATURES` extended with all seven so
  XGBoost/LightGBM see them; missing-value-aware splits handle the
  per-source nulls the same way they already handle every other
  dataset-specific column.

**Verified with real data, this entry**: `build_features.py --sample
200000` ran end-to-end (400,255 rows total after also running
`inject_attacks.py --n-per-family 20`); manifest confirms exactly 50%
null rate for all seven graph columns (the IEEE-CIS half) and the PaySim
half shows real, non-degenerate variation (`graph_dst_in_degree` ranged
1-84 in the 200k-row sample, with a real merchant-vs-customer degree
skew; `graph_src_pass_through_ratio` was uniformly 0 in this small,
early-timestep sample -- expected, since almost no account both sent and
received within a 200k-row/early-`step` window, not a bug; the full run
will show real variation). For `mule_network`, graph features are 100%
populated with real per-case topology (verified against two real
generated case files: the fan-out relay node in a `distributed_beneficiaries`
case correctly shows `graph_src_out_degree` 2 or 3 matching the real
number of final beneficiaries, `graph_dst_pass_through_ratio` near 1.0 for
every interior relay node, and 0.0 for the terminal destination nodes,
matching the GNN's own already-documented finding that `in_port` is
honestly 0 throughout -- every destination in this topology receives
exactly once). The other three generated families show exactly 0% non-null
for these columns, confirmed by direct groupby. `dataset.py::load_training_pool()`
was run against this real data end-to-end: pool shape (400255, 39), correct
`float32` dtype on all seven graph columns, correct differential null rate
by `is_generated` (50% for real data, ~21% for the generated pool in this
small 4-family/80-case verification run -- consistent with `mule_network`
being 1 of 4 families). No NaNs propagated incorrectly, no crashes,
`train_val_split` succeeded.

**Update -- real full-scale run completed** (see `docs/EVALUATION_RESULTS.md`'s
"Graph-topology features -- real before/after comparison" entry for the full
numbers). Two real bugs surfaced and were fixed before this run succeeded,
both the same underlying mistake at two different layers: `build_features.py`
was filling "this dataset doesn't have that column" gaps with a bare `np.nan`
(Python float, defaults to float64); `combine_and_save()`'s `pd.concat()`
then silently promoted the WHOLE combined column -- all 6.95M rows -- to
float64 whenever the other side was float32, which crashed
`train_xgboost.py` with `Unable to allocate 1.35 GiB`. Confirmed directly via
`pyarrow.parquet.read_schema()`: 14 columns were stored as `double` where
they should have been `float` (7 pre-existing, 7 newly introduced by this
round's own graph features using the same bare-`np.nan` pattern). Fixed by
using `np.float32(np.nan)` everywhere a numeric column is filled for the
dataset that doesn't have it, plus a smaller, separate real fix in
`dataset.py::load_training_pool()` (normalizing dtypes on each source frame
before concatenating real+generated, since `attacks_train.parquet` round-trips
some columns as pandas nullable `Float64`). On the real 6,958,023-row pool:
**XGBoost PR-AUC improved 0.5114 -> 0.6020 (+17.7% relative)**, a real,
meaningful gain consistent with the published GFP+XGBoost finding that
motivated this work; **LightGBM was essentially flat** (PR-AUC 0.6078 ->
0.6066) on the same features and same data -- an honest, mixed result, not
uniform success across both tree models.
