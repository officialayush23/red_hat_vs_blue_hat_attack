# Evaluation Results

Recorded automatically by each training/evaluation script -- do not hand-edit
numbers here, re-run the script instead.

## XGBoost -- validation split (Stage 5, ordinary train/val, not adversarial)

- Threshold: 0.5249
- Precision: 0.9803
- Recall: 0.3834
- F1: 0.5512
- ROC-AUC: 0.9862
- PR-AUC: 0.5114
- False positive rate: 0.0038%
- Train set: 5,566,418 rows / Validation set: 1,391,605 rows (6,748 fraud)

## LightGBM -- validation split (Stage 5, ordinary train/val, not adversarial)

- Threshold: 0.9832
- Precision: 0.8950
- Recall: 0.4157
- F1: 0.5677
- ROC-AUC: 0.9903
- PR-AUC: 0.6078
- False positive rate: 0.0238%
- Train set: 5,566,418 rows / Validation set: 1,391,605 rows (6,748 fraud)

## Autoencoder -- validation split (Stage 5, ordinary train/val, not adversarial)

- Anomaly-score threshold (reconstruction MSE): 0.056916
- Precision: 0.5983
- Recall: 0.2002
- F1: 0.3000
- ROC-AUC: 0.9271
- PR-AUC: 0.2563
- False positive rate: 0.0655%
- Trained on 5,539,427 legitimate rows only / Validation set: 1,391,605 rows (6,748 fraud)

## voice_spoof_detector (garystafford/wav2vec2-deepfake-voice-detector) -- Principle 11 evidence-gate run

- Precision: 0.7143
- Recall: 0.9756
- F1: 0.8247
- ROC-AUC: 0.9095
- PR-AUC: 0.9403
- False positive rate (bonafide flagged as spoof): 50.0000%
- n_bonafide=64 (LibriSpeech sample -- small-N caveat, see script docstring), n_spoof=82
- train split recall: 0.9762 (n=42)
- held_out split recall: 0.9750 (n=40)

## document_consistency_detector (PaddleOCR-VL + QR cross-check) -- Principle 11 evidence-gate run

- Precision: 0.8507
- Recall: 0.7125
- F1: 0.7755
- ROC-AUC: 0.7969
- PR-AUC: 0.8297
- False positive rate (bonafide flagged as tampered): 25.0000%
- n_bonafide=40 (self-generated, see script docstring), n_fraud=80
- train split recall: 0.4250 (n=40)
- held_out split recall: 1.0000 (n=40)

**Note (2026-08-30, added by hand, not machine-generated -- explains the numbers above, does not alter them):**
Run on Google Colab (T4 GPU) rather than locally. Four distinct low-level
Windows errors chained on paddlepaddle-gpu locally (WinError 127 DLL
collision between torch and paddle's bundled CUDA DLLs -> cudnn 9.9-vs-9.5
version mismatch -> opencv-python/opencv-contrib-python package collision
-> CUDNN_STATUS_EXECUTION_FAILED), each fixed in turn but a new one
appearing every time -- real evidence (pagefile: 10.8GB allocated, ~2.3GB
peak used; 7.3GB RAM free) ruled out memory/commit-limit as the cause, so
Colab (Linux, no Windows DLL search-order machinery) was used instead. See
docs/FUTURE_INTEGRATIONS.md item 2 for the full trail. The detector and
metrics code that ran in Colab are byte-for-byte the same files as in this
repo (backend/defend/pretrained/document_consistency_detector.py,
backend/evaluation/metrics.py), not a reimplementation.

The train (0.4250) vs held_out (1.0000) recall gap is a real, expected
structural finding, not a bug: this detector's score is the fraction of
OCR-extracted fields that mismatch the QR payload, thresholded at 0.5.
held_out cases tamper 2 fields simultaneously (e.g. bank_account +
qr_payload), pushing the mismatched fraction at or above 0.5 reliably.
train cases tamper exactly 1 of the 4 comparable fields, so the mismatch
fraction is typically ~0.25 -- structurally below the 0.5 threshold unless
OCR also fails to extract other fields. In other words: this detector is
very reliable against multi-field tampering and comparatively weak against
a single subtly altered field, which is an honest limitation worth stating
plainly rather than only reporting the blended overall recall (0.7125).
The 25% false-positive rate (10/40 bonafide flagged) is the other real
weakness worth flagging -- likely OCR misreads on genuinely bonafide
documents creating spurious field mismatches; not investigated further
under the deadline, a candidate follow-up post-submission.

## phishing_classifier (TF-IDF + LogisticRegression) -- validation split (Stage 5, ordinary train/val, not adversarial)

- Trained on: difraud/difraud phishing + sms domains (real labeled data, MIT license)
- Threshold: 0.4808
- Precision: 0.9505
- Recall: 0.9428
- F1: 0.9466
- ROC-AUC: 0.9933
- PR-AUC: 0.9886
- False positive rate: 2.4828%
- Train set: 17,476 rows / Validation set: 2,184 rows (734 deceptive)

## phishing_classifier (TF-IDF + LogisticRegression) -- Principle 11 evidence-gate run

- Precision: 0.6989
- Recall: 0.8125
- F1: 0.7514
- ROC-AUC: 0.5922
- PR-AUC: 0.8011
- False positive rate (bonafide flagged as phishing): 70.0000%
- n_bonafide=40 (self-generated, see script docstring), n_fraud=80
- train split recall: 1.0000 (n=40)
- held_out split recall: 0.6250 (n=40)
- Caveat: classifier trains only on real difraud/difraud text (Stage 5); this scores it against our own generated phishing_scam artifacts it has never seen -- a genuine generalization test, not a data-leakage-inflated number.

## phishing_classifier (TF-IDF + LogisticRegression) -- validation split (Stage 5, ordinary train/val, not adversarial)

- Trained on: difraud/difraud phishing + sms domains (real labeled data, MIT license)
- Threshold: 0.5285
- Precision: 0.9619
- Recall: 0.9292
- F1: 0.9453
- ROC-AUC: 0.9935
- PR-AUC: 0.9887
- False positive rate: 1.8621%
- Train set: 17,476 rows / Validation set: 2,184 rows (734 deceptive)

## phishing_classifier (TF-IDF + LogisticRegression) -- Principle 11 evidence-gate run

- Precision: 0.8557
- Recall: 0.8300
- F1: 0.8426
- ROC-AUC: 0.8040
- PR-AUC: 0.9110
- False positive rate (bonafide flagged as phishing): 28.0000%
- n_bonafide=100 (self-generated, see script docstring), n_fraud=200
- train split recall: 1.0000 (n=100)
- held_out split recall: 0.6600 (n=100)
- Caveat: classifier trains only on real difraud/difraud text (Stage 5); this scores it against our own generated phishing_scam artifacts it has never seen -- a genuine generalization test, not a data-leakage-inflated number.

## phishing_classifier (TF-IDF + LogisticRegression) -- Principle 11 evidence-gate run

- Precision: 0.8557
- Recall: 0.8300
- F1: 0.8426
- ROC-AUC: 0.8040
- PR-AUC: 0.9110
- False positive rate (bonafide flagged as phishing): 28.0000%
- n_bonafide=100 (self-generated, see script docstring), n_fraud=200
- train split recall: 1.0000 (n=100)
- held_out split recall: 0.6600 (n=100)
- Caveat: classifier trains only on real difraud/difraud text (Stage 5); this scores it against our own generated phishing_scam artifacts it has never seen -- a genuine generalization test, not a data-leakage-inflated number.

## phishing_classifier (TF-IDF + LogisticRegression) -- validation split (Stage 5, ordinary train/val, not adversarial)

- Trained on: difraud/difraud phishing + sms domains (real labeled data, MIT license)
- Threshold: 0.4629
- Precision: 0.9479
- Recall: 0.9428
- F1: 0.9454
- ROC-AUC: 0.9933
- PR-AUC: 0.9885
- False positive rate: 2.6207%
- Train set: 17,476 rows / Validation set: 2,184 rows (734 deceptive)

## phishing_classifier (TF-IDF + intent/URL features + LogisticRegression) -- Principle 11 evidence-gate run

n_bonafide=100 (self-generated, negative control -- see script docstring). 'overall' = bonafide vs. all generated phishing cases; 'train' / 'held_out' = bonafide vs. just that split's phishing cases (bonafide is the shared negative class in every column, so a bare per-column precision/recall on bonafide alone isn't mathematically meaningful).

| Metric | overall | train | held-out |
|---|---|---|---|
| Precision | 0.8152 | 0.7194 | 0.6486 |
| Recall | 0.8600 | 1.0000 | 0.7200 |
| F1 | 0.8370 | 0.8368 | 0.6825 |
| ROC-AUC | 0.8334 | 0.9905 | 0.6763 |
| PR-AUC | 0.9300 | 0.9908 | 0.7461 |
| FPR (bonafide flagged as phishing) | 39.00% | 39.00% | 39.00% |
| n_positive (phishing cases in this column) | 200 | 100 | 100 |

- Caveat: classifier trains only on real difraud/difraud text (Stage 5); this scores it against our own generated phishing_scam artifacts it has never seen -- a genuine generalization test, not a data-leakage-inflated number.

## phishing_classifier (TF-IDF + intent/URL features + LogisticRegression) -- Principle 11 evidence-gate run

n_bonafide=100 (self-generated, negative control -- see script docstring). 'overall' = bonafide vs. all generated phishing cases; 'train' / 'held_out' = bonafide vs. just that split's phishing cases (bonafide is the shared negative class in every column, so a bare per-column precision/recall on bonafide alone isn't mathematically meaningful).

| Metric | overall | train | held-out |
|---|---|---|---|
| Precision | 0.8152 | 0.7194 | 0.6486 |
| Recall | 0.8600 | 1.0000 | 0.7200 |
| F1 | 0.8370 | 0.8368 | 0.6825 |
| ROC-AUC | 0.8334 | 0.9905 | 0.6763 |
| PR-AUC | 0.9300 | 0.9908 | 0.7461 |
| FPR (bonafide flagged as phishing) | 39.00% | 39.00% | 39.00% |
| n_positive (phishing cases in this column) | 200 | 100 | 100 |

- Caveat: classifier trains only on real difraud/difraud text (Stage 5); this scores it against our own generated phishing_scam artifacts it has never seen -- a genuine generalization test, not a data-leakage-inflated number.

## xgboost -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9935
- Recall: 0.9878
- F1: 0.9906
- ROC-AUC: 0.9998
- PR-AUC: 0.9877
- False positive rate (against Stage-5 validation-split legit rows): 0.0038%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 0.9592 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## lightgbm -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9606
- Recall: 1.0000
- F1: 0.9799
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (against Stage-5 validation-split legit rows): 0.0238%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## autoencoder -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.8954
- Recall: 0.9672
- F1: 0.9299
- ROC-AUC: 0.9997
- PR-AUC: 0.9674
- False positive rate (against Stage-5 validation-split legit rows): 0.0655%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 0.8242 (n_fraud_rows=1200)
- account_takeover recall: 0.9675 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## Interpretation note -- adversarial recall vs. Stage-5 validation recall (added by hand, 2026-08-30, not script-generated -- see header)

The three sections above show 0.96-1.00 recall on Section 8's held-out set. That is a real, honestly-computed number, but it should not be read as "these models got dramatically better" -- it answers a narrower question than it looks like it does. Stage-5 validation recall (see the XGBoost/LightGBM/Autoencoder sections earlier in this file) was 0.20-0.42, computed on a pool mixing genuinely hard real PaySim/IEEE-CIS fraud with generated fraud. `attacks_held_out.parquet` is 100% generated by construction (Principle 13 keeps the fraud *label* out of the model, but the mutation engine writes the *feature values* -- `hop_count`, `shared_device`, `timing_irregular`, etc. -- directly and deliberately, per attack family and combination). So high adversarial recall most likely reflects that a rule-generated attack case is structurally distinguishable from a real legitimate transaction using the same engineered features the model reads, not that these models would catch a real adversary attempting the same behavioral pattern in the wild. Both numbers are real and both are worth keeping; they measure different things.

The one number here that IS the real, actionable Section 8 step 5 finding ("identify the weakest family/combination"): **Autoencoder / transaction_fraud, recall 0.8242** -- the single meaningfully-sub-1.0 result across all three models and four families (XGBoost's synthetic_identity at 0.9592 is a distant second). That is the honest weak point to target in a step-6 mutation round, not any of the near-perfect numbers.

## xgboost -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9935
- Recall: 0.9878
- F1: 0.9906
- ROC-AUC: 0.9998
- PR-AUC: 0.9877
- False positive rate (against Stage-5 validation-split legit rows): 0.0038%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 0.9592 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## lightgbm -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9606
- Recall: 1.0000
- F1: 0.9799
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (against Stage-5 validation-split legit rows): 0.0238%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## autoencoder -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.8954
- Recall: 0.9672
- F1: 0.9299
- ROC-AUC: 0.9997
- PR-AUC: 0.9674
- False positive rate (against Stage-5 validation-split legit rows): 0.0655%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 0.8242 (n_fraud_rows=1200)
- account_takeover recall: 0.9675 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## fusion (XGBoost + LightGBM + Autoencoder, weighted by real Stage-5 ROC-AUC) -- Section 6 evidence gate, held-out combinations

- Weights: xgboost=0.3396, lightgbm=0.3411, autoencoder=0.3193
- Threshold: 0.5184 (picked on Stage-5 validation's fused scores, not on held-out data itself)
- Precision: 0.9385
- Recall: 1.0000
- F1: 0.9683
- ROC-AUC: 1.0000
- PR-AUC: 0.9999
- False positive rate: 0.0380%
- n_legit=1384857, n_fraud=8025 (held-out combinations, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Compare against the individual xgboost_adversarial_eval / lightgbm_adversarial_eval / autoencoder_adversarial_eval sections above -- same held-out rows, same legit baseline, so this is a fair apples-to-apples fusion-vs-best-single-model comparison.
- Scope: weighted multi-model combination only. Customer-behavior corroboration (defend.fusion.behavioral_adjustment) is NOT exercised here -- no real customer_id linkage exists yet for generated cases (Phase 2.5). See defend/fusion.py.

## Section 8 step 6 -- targeted mutation round: autoencoder / transaction_fraud

- Before (step 5, original held-out combo): recall=0.8242
- Original combo: {'amount': 'mid', 'velocity': 'moderate', 'merchant_category': 'new', 'time_of_day': 'off_hours'}
- Hardened combo: {'amount': 'mid', 'velocity': 'moderate', 'merchant_category': 'new', 'time_of_day': 'normal'}
- Reason: removed the off-hours timing tell (time_of_day: off_hours -> normal) -- tests whether the structural/categorical fraud signal alone, without an obvious numeric-time anomaly, evades detection even more
- After (round 2, 1,200 new rows / 400 cases): recall=0.8258, precision=0.5221, roc_auc=0.9983
- Delta: +0.0017

## GNN (Task #33, round 4) -- Colab-reported, not yet independently re-verified (added by hand, 2026-08-31, not script-generated -- see header)

Real, honestly-reported numbers from an actual Colab run of
`notebooks/train_gnn_mule_network.ipynb` after adopting reverse message
passing + port numbering (Egressy et al. AAAI 2024, arXiv:2306.11586) --
see `docs/DATASETS.md`'s round-4 entry for the full research context.
Saved verbatim to `backend/defend/models/metrics.json` under
`gnn_colab_round4_reported` / `gnn_adversarial_eval_colab_round4_reported`.
**Not yet independently re-verified** -- that requires downloading the
matching `gnn.pt` from this Colab run into `backend/defend/models/gnn.pt`
(overwriting the round-3 file currently there) and running
`backend/evaluation/eval_gnn.py`, per this file's own two-independent-runs
evidence-gate convention.

- IBM AML held-out test (n=1,015,669 edges, 1,797 real laundering edges):
  ROC-AUC=0.5669, PR-AUC=0.0026, minority-class F1=0.0079, at the
  best-F1 threshold (0.7980): precision=0.0369, recall=0.0045, FPR=0.0002%.
- **Honest comparison against the published HI-Small baselines**
  (arXiv:2306.16424 Table 2): GIN F1=28.7%, GIN+edge-updates F1=47.7%,
  PNA F1=56.8%, graph-features+XGBoost F1=63.2%. This round-4 run's
  F1=0.79% is not competitive with any of them, despite correctly
  implementing both of the paper's real, published techniques. ROC-AUC
  is essentially unchanged from round 3 (0.5669 -> 0.5669, i.e.
  identical to 4 decimal places) -- reverse message passing and port
  numbering did not move this run's IBM AML held-out performance in any
  measurable way.
- `mule_network` held-out recall (400 real generated cases, same frozen
  weights, IBM-AML-selected threshold): still 0/400 -- unchanged from
  round 3. The one real, if modest, improvement: `percentile_vs_ibm_aml_test_scores`
  rose from round 3's 0.9561 to **0.9793** -- on average a `mule_network`
  case now outscores 97.93% of real IBM AML test transactions (up from
  95.6%), so the model's *ranking* of mule cases relative to the general
  IBM AML population did improve, even though recall at this specific
  borrowed threshold did not.
- **What this means, honestly**: round 4's real published techniques
  produced a real (if small) ranking improvement on the cross-domain
  metric, but did not close anything close to the gap to the published
  GFP+XGBoost baseline (63.2% F1) that motivated checking the literature
  in the first place, nor to the July-2026 production LightGBM system
  (arXiv:2607.17586, precision 0.909/recall 0.816). This is real,
  disappointing-but-informative evidence reinforcing that decision's
  premise: for this exact task, a from-scratch GNN -- even implementing
  the specific published architectural fixes for it -- is not
  outperforming a well-featured tree model, on either the literature's
  own benchmark or this project's real numbers. See `docs/DATASETS.md`
  for the graph-feature-engineered XGBoost/LightGBM work that is the
  other half of the "do both" decision, and is expected (per the
  published GFP+XGBoost F1=63.2% result) to be the stronger path.

## XGBoost -- validation split (Stage 5, ordinary train/val, not adversarial)

- Threshold: 0.9825
- Precision: 0.8977
- Recall: 0.4133
- F1: 0.5660
- ROC-AUC: 0.9899
- PR-AUC: 0.6020
- False positive rate: 0.0230%
- Train set: 5,566,418 rows / Validation set: 1,391,605 rows (6,748 fraud)

## LightGBM -- validation split (Stage 5, ordinary train/val, not adversarial)

- Threshold: 0.9814
- Precision: 0.8589
- Recall: 0.4238
- F1: 0.5676
- ROC-AUC: 0.9903
- PR-AUC: 0.6066
- False positive rate: 0.0339%
- Train set: 5,566,418 rows / Validation set: 1,391,605 rows (6,748 fraud)

## Graph-topology features -- real before/after comparison (Task #33 "do both", tabular half)

The XGBoost/LightGBM sections immediately above are the FIRST real full-scale
(6,958,023-row) run with the seven `graph_src_*`/`graph_dst_*`/`graph_in_port`
features added (`docs/DATASETS.md`'s graph-feature entry). Comparing them
against the real pre-graph-feature baseline still recorded earlier in this
file (same real data otherwise, same 6,748 validation-fraud count, same
1,391,605-row validation split):

- **XGBoost**: PR-AUC 0.5114 -> **0.6020** (+0.0906, ~+17.7% relative --
  the largest single move in this comparison), ROC-AUC 0.9862 -> 0.9899
  (+0.0037), F1 0.5512 -> 0.5660 (+0.0148), recall 0.3834 -> 0.4133
  (+0.0299). A real, meaningful improvement, and directionally consistent
  with the published finding that motivated this work (Altman, Egressy et
  al., arXiv:2306.16424: graph-feature-engineered XGBoost beat every GNN
  baseline tested on this task's own benchmark dataset).
- **LightGBM**: PR-AUC 0.6078 -> 0.6066 (-0.0012), ROC-AUC 0.9903 -> 0.9903
  (unchanged), F1 0.5677 -> 0.5676 (unchanged), recall 0.4157 -> 0.4238
  (+0.0081, small). Essentially flat -- the new features did not
  meaningfully help LightGBM on this validation split, in contrast to
  XGBoost's real gain from the same seven columns on the same data.
- **Honest read**: a mixed, not uniform, result -- worth stating plainly
  rather than rounding up. One real hypothesis for the split, not yet
  tested: XGBoost's default tree-growth policy may be finding sparser,
  more targeted splits on ~50%-null features (paysim-only,
  three-of-four-generated-families-null) than LightGBM's leaf-wise growth
  does with its own default settings -- untested, flagged for a future
  pass rather than acted on here. Precision dropped for XGBoost (0.9803
  -> 0.8977) because its own best-F1 threshold moved (0.5249 -> 0.9825,
  automatically re-selected by the same script both times) -- not a
  like-for-like precision comparison at a fixed threshold, PR-AUC is the
  threshold-independent number to trust here.
- Not yet re-run: `train_autoencoder.py` (unaffected by these tabular
  features, but should be re-run so `defend/models/metrics.json` reflects
  the same real data snapshot across all three models before the next
  Section 8 adversarial-evaluation pass), and Section 8's
  `run_adversarial_eval.py` itself (Stage 7) -- these Stage-5 validation
  numbers are not the adversarial held-out numbers; see this file's own
  "Interpretation note" above for why the two should not be conflated.

## Autoencoder -- validation split (Stage 5, ordinary train/val, not adversarial)

- Anomaly-score threshold (reconstruction MSE): 0.119589
- Precision: 0.4736
- Recall: 0.1649
- F1: 0.2447
- ROC-AUC: 0.9425
- PR-AUC: 0.2150
- False positive rate: 0.0893%
- Trained on 5,539,427 legitimate rows only / Validation set: 1,391,605 rows (6,748 fraud)

## xgboost -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9565
- Recall: 0.8713
- F1: 0.9119
- ROC-AUC: 0.9987
- PR-AUC: 0.9262
- False positive rate (against Stage-5 validation-split legit rows): 0.0230%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 0.9133 (n_fraud_rows=2400)
- mule_network recall: 0.7080 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## lightgbm -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9447
- Recall: 1.0000
- F1: 0.9715
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (against Stage-5 validation-split legit rows): 0.0339%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## autoencoder -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.8417
- Recall: 0.8196
- F1: 0.8305
- ROC-AUC: 0.9991
- PR-AUC: 0.9166
- False positive rate (against Stage-5 validation-split legit rows): 0.0893%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 0.4300 (n_fraud_rows=1200)
- account_takeover recall: 0.5225 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## fusion (XGBoost + LightGBM + Autoencoder, weighted by real Stage-5 ROC-AUC) -- Section 6 evidence gate, held-out combinations

- Weights: xgboost=0.3387, lightgbm=0.3388, autoencoder=0.3225
- Threshold: 0.6756 (picked on Stage-5 validation's fused scores, not on held-out data itself)
- Precision: 0.9621
- Recall: 1.0000
- F1: 0.9807
- ROC-AUC: 1.0000
- PR-AUC: 0.9994
- False positive rate: 0.0228%
- n_legit=1384857, n_fraud=8025 (held-out combinations, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Compare against the individual xgboost_adversarial_eval / lightgbm_adversarial_eval / autoencoder_adversarial_eval sections above -- same held-out rows, same legit baseline, so this is a fair apples-to-apples fusion-vs-best-single-model comparison.
- Scope: weighted multi-model combination only. Customer-behavior corroboration (defend.fusion.behavioral_adjustment) is NOT exercised here -- no real customer_id linkage exists yet for generated cases (Phase 2.5). See defend/fusion.py.

## Section 8 step 6 -- targeted mutation round: autoencoder / transaction_fraud

- Before (step 5, original held-out combo): recall=0.4300
- Original combo: {'amount': 'mid', 'velocity': 'moderate', 'merchant_category': 'new', 'time_of_day': 'off_hours'}
- Hardened combo: {'amount': 'mid', 'velocity': 'moderate', 'merchant_category': 'new', 'time_of_day': 'normal'}
- Reason: removed the off-hours timing tell (time_of_day: off_hours -> normal) -- tests whether the structural/categorical fraud signal alone, without an obvious numeric-time anomaly, evades detection even more
- After (round 2, 1,200 new rows / 400 cases): recall=0.4333, precision=0.2960, roc_auc=0.9958
- Delta: +0.0033

## Section 8 step 6 -- targeted mutation round: autoencoder / transaction_fraud

- Before (step 5, original held-out combo): recall=0.4300
- Original combo: {'amount': 'mid', 'velocity': 'moderate', 'merchant_category': 'new', 'time_of_day': 'off_hours'}
- Hardened combo: {'amount': 'mid', 'velocity': 'moderate', 'merchant_category': 'new', 'time_of_day': 'normal'}
- Reason: removed the off-hours timing tell (time_of_day: off_hours -> normal) -- tests whether the structural/categorical fraud signal alone, without an obvious numeric-time anomaly, evades detection even more
- After (round 2, 1,200 new rows / 400 cases): recall=0.4333, precision=0.2960, roc_auc=0.9958
- Delta: +0.0033

## Section 8 step 6 -- targeted mutation round: autoencoder / transaction_fraud

- Before (step 5, original held-out combo): recall=0.4300
- Original combo: {'amount': 'mid', 'velocity': 'moderate', 'merchant_category': 'new', 'time_of_day': 'off_hours'}
- Hardened combo: {'amount': 'low', 'merchant_category': 'new', 'time_of_day': 'business_hours', 'velocity': 'moderate'}
- Reason: The autoencoder's low recall (0.43) on off-hours mid-amount transactions indicates it relies on strong distribution drift to generate high reconstruction error.; Masking the transaction within standard business hours and lowering the amount reduces its baseline anomaly score, directly targeting the autoencoder's tendency to treat low-value daytime events as benign.
- After (round 2, 1,200 new rows / 400 cases): recall=0.4050, precision=0.2821, roc_auc=0.9966
- Delta: -0.0250

## GNN (Task #33) -- local re-verification of the Colab-trained model

- Independent, local re-run of the 1270 real held-out mule_network cases, using the frozen weights saved from notebooks/train_gnn_mule_network.ipynb.
- recall=0.0000 at decision_threshold=0.7980 (threshold selected on IBM AML's own held-out split, see the notebook).
- This is a second, independent check against the Colab run's own reported number in gnn_metrics_snippet.json -- see docs/DATASETS.md.

## voice_spoof_detector (garystafford/wav2vec2-deepfake-voice-detector) -- Principle 11 evidence-gate run

- Decision threshold: 0.9761 (best_f1_threshold on bonafide + train-split spoof only, then applied unchanged to held_out -- same calibrate-on-train/apply-to-held_out pattern as run_adversarial_eval.py's frozen tabular thresholds, not re-picked on held_out)
- Precision: 0.8933
- Recall: 0.8171
- F1: 0.8535
- ROC-AUC: 0.9095
- PR-AUC: 0.9403
- False positive rate (bonafide flagged as spoof): 12.5000%
- n_bonafide=64 (LibriSpeech sample -- small-N caveat, see script docstring), n_spoof=82
- train split recall: 0.8333 (n=42)
- held_out split recall: 0.8000 (n=40)

## voice_spoof_detector (garystafford/wav2vec2-deepfake-voice-detector) -- Principle 11 evidence-gate run

- Decision threshold: 0.9761 (best_f1_threshold on bonafide + train-split spoof only, then applied unchanged to held_out -- same calibrate-on-train/apply-to-held_out pattern as run_adversarial_eval.py's frozen tabular thresholds, not re-picked on held_out)
- Precision: 0.8933
- Recall: 0.8171
- F1: 0.8535
- ROC-AUC: 0.9095
- PR-AUC: 0.9403
- False positive rate (bonafide flagged as spoof): 12.5000%
- n_bonafide=64 (LibriSpeech sample -- small-N caveat, see script docstring), n_spoof=82
- train split recall: 0.8333 (n=42)
- held_out split recall: 0.8000 (n=40)

## document_consistency_detector (PaddleOCR-VL + QR cross-check) -- Principle 11 evidence-gate run (round 2)

- Run on Google Colab (T4 GPU) -- local Windows inference (paddleocr_env) hit a new, distinct
  failure this round (os error 1455, a paging-file/virtual-memory commitment-limit error at
  first inference), separate from the earlier DLL-collision class of errors. Detector and
  metrics code run unmodified from the repo; only the image-path separator bug
  (backslash-in-JSON, Windows-generated case files vs. Linux/Colab PurePosixPath) required a
  one-line fix in evaluation/eval_document_consistency.py.
- Decision threshold: 0.2500 (best_f1_threshold on bonafide + train-split fraud only, then applied unchanged to held_out -- same calibrate-on-train/apply-to-held_out pattern as run_adversarial_eval.py's frozen tabular thresholds, not re-picked on held_out -- round 1 used an uncalibrated 0.5 default)
- Precision: 0.8795
- Recall: 0.9125 (round 1: 0.7125)
- F1: 0.8957 (round 1: 0.7755)
- ROC-AUC: 0.7969
- PR-AUC: 0.8297
- False positive rate (bonafide flagged as tampered): 25.0000% (unchanged from round 1 -- the
  same 10/40 bonafide docs were misflagged at both thresholds; the field-mismatch score is
  quantized and none of them landed exactly between 0.25 and 0.5)
- n_bonafide=40 (self-generated, see script docstring), n_fraud=80
- train split recall: 0.8250 (n=40) (round 1: 0.4250)
- held_out split recall: 1.0000 (n=40) (round 1: 1.0000, unchanged)

## video_kyc_detector (facenet-pytorch MTCNN + InceptionResnetV1/VGGFace2) -- Principle 11 evidence-gate run

- Decision threshold: 0.6374 (best_f1_threshold on train-split cases only, then applied unchanged to held_out)
- n_cases=6 (dataset still growing -- see script docstring)
- Precision: 1.0000
- Recall: 1.0000
- F1: 1.0000
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (bonafide flagged as impersonation): 0.0000%
- train split (n=4, n_positive=2): recall=1.0000, precision=1.0000
- held_out split (n=2, n_positive=1): recall=1.0000, precision=1.0000

## video_kyc_detector (facenet-pytorch MTCNN + InceptionResnetV1/VGGFace2) -- Principle 11 evidence-gate run

- Decision threshold: 0.6374 (best_f1_threshold on train-split cases only, then applied unchanged to held_out)
- n_cases=6 (dataset still growing -- see script docstring)
- Precision: 1.0000
- Recall: 1.0000
- F1: 1.0000
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (bonafide flagged as impersonation): 0.0000%
- train split (n=4, n_positive=2): recall=1.0000, precision=1.0000
- held_out split (n=2, n_positive=1): recall=1.0000, precision=1.0000

## phishing_classifier (TF-IDF + intent/URL features + LogisticRegression) -- Principle 11 evidence-gate run

n_bonafide=100 (self-generated, negative control -- see script docstring). 'overall' = bonafide vs. all generated phishing cases; 'train' / 'held_out' = bonafide vs. just that split's phishing cases (bonafide is the shared negative class in every column, so a bare per-column precision/recall on bonafide alone isn't mathematically meaningful).

| Metric | overall | train | held-out |
|---|---|---|---|
| Precision | 0.8152 | 0.7194 | 0.6486 |
| Recall | 0.8600 | 1.0000 | 0.7200 |
| F1 | 0.8370 | 0.8368 | 0.6825 |
| ROC-AUC | 0.8334 | 0.9905 | 0.6763 |
| PR-AUC | 0.9300 | 0.9908 | 0.7461 |
| FPR (bonafide flagged as phishing) | 39.00% | 39.00% | 39.00% |
| n_positive (phishing cases in this column) | 200 | 100 | 100 |

- Caveat: classifier trains only on real difraud/difraud text (Stage 5); this scores it against our own generated phishing_scam artifacts it has never seen -- a genuine generalization test, not a data-leakage-inflated number.

## GNN (Task #33) -- local re-verification of the Colab-trained model

- Independent, local re-run of the 1270 real held-out mule_network cases, using the frozen weights saved from notebooks/train_gnn_mule_network.ipynb.
- recall=0.0024 at decision_threshold=0.8222 (threshold selected on IBM AML's own held-out split, see the notebook).
- This is a second, independent check against the Colab run's own reported number in gnn_metrics_snippet.json -- see docs/DATASETS.md.

## fusion (XGBoost + LightGBM + Autoencoder, weighted by real Stage-5 ROC-AUC) -- Section 6 evidence gate, held-out combinations

- Weights: xgboost=0.3387, lightgbm=0.3388, autoencoder=0.3225
- Threshold: 0.6756 (picked on Stage-5 validation's fused scores, not on held-out data itself)
- Precision: 0.9621
- Recall: 1.0000
- F1: 0.9807
- ROC-AUC: 1.0000
- PR-AUC: 0.9994
- False positive rate: 0.0228%
- n_legit=1384857, n_fraud=8025 (held-out combinations, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Compare against the individual xgboost_adversarial_eval / lightgbm_adversarial_eval / autoencoder_adversarial_eval sections above -- same held-out rows, same legit baseline, so this is a fair apples-to-apples fusion-vs-best-single-model comparison.
- Scope: weighted multi-model combination only. Customer-behavior corroboration (defend.fusion.behavioral_adjustment) is NOT exercised here -- no real customer_id linkage exists yet for generated cases (Phase 2.5). See defend/fusion.py.

## xgboost -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9565
- Recall: 0.8713
- F1: 0.9119
- ROC-AUC: 0.9987
- PR-AUC: 0.9262
- False positive rate (against Stage-5 validation-split legit rows): 0.0230%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 0.9133 (n_fraud_rows=2400)
- mule_network recall: 0.7080 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## lightgbm -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9447
- Recall: 1.0000
- F1: 0.9715
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (against Stage-5 validation-split legit rows): 0.0339%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## autoencoder -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.8417
- Recall: 0.8196
- F1: 0.8305
- ROC-AUC: 0.9991
- PR-AUC: 0.9166
- False positive rate (against Stage-5 validation-split legit rows): 0.0893%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 0.4300 (n_fraud_rows=1200)
- account_takeover recall: 0.5225 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## GNN (Task #33) -- local re-verification of the Colab-trained model

- Independent, local re-run of the 1580 real held-out mule_network cases, using the frozen weights saved from notebooks/train_gnn_mule_network.ipynb.
- recall=0.0019 at decision_threshold=0.8222 (threshold selected on IBM AML's own held-out split, see the notebook).
- This is a second, independent check against the Colab run's own reported number in gnn_metrics_snippet.json -- see docs/DATASETS.md.

## fusion (XGBoost + LightGBM + Autoencoder, weighted by real Stage-5 ROC-AUC) -- Section 6 evidence gate, held-out combinations

- Weights: xgboost=0.3387, lightgbm=0.3388, autoencoder=0.3225
- Threshold: 0.6756 (picked on Stage-5 validation's fused scores, not on held-out data itself)
- Precision: 0.9621
- Recall: 1.0000
- F1: 0.9807
- ROC-AUC: 1.0000
- PR-AUC: 0.9994
- False positive rate: 0.0228%
- n_legit=1384857, n_fraud=8025 (held-out combinations, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Compare against the individual xgboost_adversarial_eval / lightgbm_adversarial_eval / autoencoder_adversarial_eval sections above -- same held-out rows, same legit baseline, so this is a fair apples-to-apples fusion-vs-best-single-model comparison.
- Scope: weighted multi-model combination only. Customer-behavior corroboration (defend.fusion.behavioral_adjustment) is NOT exercised here -- no real customer_id linkage exists yet for generated cases (Phase 2.5). See defend/fusion.py.

## xgboost -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9565
- Recall: 0.8713
- F1: 0.9119
- ROC-AUC: 0.9987
- PR-AUC: 0.9262
- False positive rate (against Stage-5 validation-split legit rows): 0.0230%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 0.9133 (n_fraud_rows=2400)
- mule_network recall: 0.7080 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## lightgbm -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9447
- Recall: 1.0000
- F1: 0.9715
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (against Stage-5 validation-split legit rows): 0.0339%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## autoencoder -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.8417
- Recall: 0.8196
- F1: 0.8305
- ROC-AUC: 0.9991
- PR-AUC: 0.9166
- False positive rate (against Stage-5 validation-split legit rows): 0.0893%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 0.4300 (n_fraud_rows=1200)
- account_takeover recall: 0.5225 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## Section 8 step 6 -- targeted mutation round: autoencoder / transaction_fraud

- Before (step 5, original held-out combo): recall=0.4300
- Original combo: {'amount': 'mid', 'velocity': 'moderate', 'merchant_category': 'new', 'time_of_day': 'off_hours'}
- Hardened combo: {'amount': 'mid', 'merchant_category': 'new', 'time_of_day': 'business_hours', 'velocity': 'low'}
- Reason: The autoencoder relies on reconstruction error to flag anomalies, but already exhibits a low recall of 0.43 under off-hours and moderate velocity conditions.; Lowering the velocity to 'low' and moving the time to 'business_hours' significantly reduces the statistical anomaly footprint, likely decreasing reconstruction error and allowing stealthier fraudulent transactions to bypass detection.
- After (round 2, 200 new rows / 200 cases): recall=0.3150, precision=0.0485, roc_auc=0.9923
- Delta: -0.1150

## voice_spoof_detector (garystafford/wav2vec2-deepfake-voice-detector) -- Principle 11 evidence-gate run

- Decision threshold: 0.9760 (best_f1_threshold on bonafide + train-split spoof only, then applied unchanged to held_out -- same calibrate-on-train/apply-to-held_out pattern as run_adversarial_eval.py's frozen tabular thresholds, not re-picked on held_out)
- Precision: 0.8701
- Recall: 0.8171
- F1: 0.8428
- ROC-AUC: 0.9056
- PR-AUC: 0.9248
- False positive rate (bonafide flagged as spoof): 11.9048%
- n_bonafide=84 (LibriSpeech sample -- small-N caveat, see script docstring), n_spoof=82
- train split recall: 0.8333 (n=42)
- held_out split recall: 0.8000 (n=40)

## video_kyc_detector (facenet-pytorch MTCNN + InceptionResnetV1/VGGFace2) -- Principle 11 evidence-gate run

- Decision threshold: 0.4811 (best_f1_threshold on train-split cases only, then applied unchanged to held_out)
- n_cases=12 (dataset still growing -- see script docstring)
- Precision: 1.0000
- Recall: 1.0000
- F1: 1.0000
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (bonafide flagged as impersonation): 0.0000%
- train split (n=8, n_positive=4): recall=1.0000, precision=1.0000
- held_out split (n=4, n_positive=2): recall=1.0000, precision=1.0000

## phishing_classifier (TF-IDF + intent/URL features + LogisticRegression) -- Principle 11 evidence-gate run

n_bonafide=200 (self-generated, negative control -- see script docstring). 'overall' = bonafide vs. all generated phishing cases; 'train' / 'held_out' = bonafide vs. just that split's phishing cases (bonafide is the shared negative class in every column, so a bare per-column precision/recall on bonafide alone isn't mathematically meaningful).

| Metric | overall | train | held-out |
|---|---|---|---|
| Precision | 0.8824 | 0.8108 | 0.7627 |
| Recall | 0.8750 | 1.0000 | 0.7500 |
| F1 | 0.8787 | 0.8955 | 0.7563 |
| ROC-AUC | 0.8416 | 0.9895 | 0.6937 |
| PR-AUC | 0.9508 | 0.9932 | 0.8097 |
| FPR (bonafide flagged as phishing) | 35.00% | 35.00% | 35.00% |
| n_positive (phishing cases in this column) | 600 | 300 | 300 |

- Caveat: classifier trains only on real difraud/difraud text (Stage 5); this scores it against our own generated phishing_scam artifacts it has never seen -- a genuine generalization test, not a data-leakage-inflated number.

## fusion (XGBoost + LightGBM + Autoencoder, weighted by real Stage-5 ROC-AUC) -- Section 6 evidence gate, held-out combinations

- Weights: xgboost=0.3387, lightgbm=0.3388, autoencoder=0.3225
- Threshold: 0.6756 (picked on Stage-5 validation's fused scores, not on held-out data itself)
- Precision: 0.9621
- Recall: 1.0000
- F1: 0.9807
- ROC-AUC: 1.0000
- PR-AUC: 0.9994
- False positive rate: 0.0228%
- n_legit=1384857, n_fraud=8025 (held-out combinations, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Compare against the individual xgboost_adversarial_eval / lightgbm_adversarial_eval / autoencoder_adversarial_eval sections above -- same held-out rows, same legit baseline, so this is a fair apples-to-apples fusion-vs-best-single-model comparison.
- Scope: weighted multi-model combination only. Customer-behavior corroboration (defend.fusion.behavioral_adjustment) is NOT exercised here -- no real customer_id linkage exists yet for generated cases (Phase 2.5). See defend/fusion.py.

## xgboost -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9565
- Recall: 0.8713
- F1: 0.9119
- ROC-AUC: 0.9987
- PR-AUC: 0.9262
- False positive rate (against Stage-5 validation-split legit rows): 0.0230%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 0.9133 (n_fraud_rows=2400)
- mule_network recall: 0.7080 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## lightgbm -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9447
- Recall: 1.0000
- F1: 0.9715
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (against Stage-5 validation-split legit rows): 0.0339%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1200)
- account_takeover recall: 1.0000 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## autoencoder -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.8417
- Recall: 0.8196
- F1: 0.8305
- ROC-AUC: 0.9991
- PR-AUC: 0.9166
- False positive rate (against Stage-5 validation-split legit rows): 0.0893%
- n_legit=1384857, n_fraud=8025 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 0.4300 (n_fraud_rows=1200)
- account_takeover recall: 0.5225 (n_fraud_rows=1600)
- synthetic_identity recall: 1.0000 (n_fraud_rows=2400)
- mule_network recall: 1.0000 (n_fraud_rows=2825)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## fusion (XGBoost + LightGBM + Autoencoder, weighted by real Stage-5 ROC-AUC) -- Section 6 evidence gate, held-out combinations

- Weights: xgboost=0.3387, lightgbm=0.3388, autoencoder=0.3225
- Threshold: 0.6756 (picked on Stage-5 validation's fused scores, not on held-out data itself)
- Precision: 0.9693
- Recall: 1.0000
- F1: 0.9844
- ROC-AUC: 1.0000
- PR-AUC: 0.9995
- False positive rate: 0.0228%
- n_legit=1384858, n_fraud=9987 (held-out combinations, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1500)
- account_takeover recall: 1.0000 (n_fraud_rows=2000)
- synthetic_identity recall: 1.0000 (n_fraud_rows=3000)
- mule_network recall: 1.0000 (n_fraud_rows=3487)
- Compare against the individual xgboost_adversarial_eval / lightgbm_adversarial_eval / autoencoder_adversarial_eval sections above -- same held-out rows, same legit baseline, so this is a fair apples-to-apples fusion-vs-best-single-model comparison.
- Scope: weighted multi-model combination only. Customer-behavior corroboration (defend.fusion.behavioral_adjustment) is NOT exercised here -- no real customer_id linkage exists yet for generated cases (Phase 2.5). See defend/fusion.py.

## behavioral_adjustment (defend/fusion.py) -- Principle 11 evidence-gate run, account_takeover held-out

- Fixed decision threshold: 30.0 (defend/fusion.py's own 'approve' band ceiling)
- n_fraud_rows=2000, of which 2000 had a real customer_id + behavior_baseline to adjust against (0 had none -- pass through unadjusted)
- BASELINE  (fused score only):   precision=0.0184  recall=1.0000  fpr=7.7197%
- ADJUSTED  (+ behavioral_adjustment): precision=0.0184  recall=1.0000  fpr=7.7197%
- Delta: precision +0.0000, recall +0.0000, fpr +0.0000%

## xgboost -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9649
- Recall: 0.8752
- F1: 0.9179
- ROC-AUC: 0.9988
- PR-AUC: 0.9352
- False positive rate (against Stage-5 validation-split legit rows): 0.0230%
- n_legit=1384858, n_fraud=9987 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1500)
- account_takeover recall: 1.0000 (n_fraud_rows=2000)
- synthetic_identity recall: 0.9137 (n_fraud_rows=3000)
- mule_network recall: 0.7169 (n_fraud_rows=3487)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## lightgbm -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.9551
- Recall: 1.0000
- F1: 0.9770
- ROC-AUC: 1.0000
- PR-AUC: 1.0000
- False positive rate (against Stage-5 validation-split legit rows): 0.0339%
- n_legit=1384858, n_fraud=9987 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 1.0000 (n_fraud_rows=1500)
- account_takeover recall: 1.0000 (n_fraud_rows=2000)
- synthetic_identity recall: 1.0000 (n_fraud_rows=3000)
- mule_network recall: 1.0000 (n_fraud_rows=3487)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## autoencoder -- Section 8 adversarial evaluation (Stage 7, frozen model, held-out combinations)

- Precision: 0.8696
- Recall: 0.8262
- F1: 0.8473
- ROC-AUC: 0.9991
- PR-AUC: 0.9281
- False positive rate (against Stage-5 validation-split legit rows): 0.0893%
- n_legit=1384858, n_fraud=9987 (held-out combinations only, transaction-row granularity)
- transaction_fraud recall: 0.4340 (n_fraud_rows=1500)
- account_takeover recall: 0.5565 (n_fraud_rows=2000)
- synthetic_identity recall: 1.0000 (n_fraud_rows=3000)
- mule_network recall: 1.0000 (n_fraud_rows=3487)
- Caveat: legit comparison rows are the Stage-5 train_val_split's validation portion (seen by XGBoost/LightGBM's early stopping, never in a gradient update) -- see this script's module docstring for the full caveat.

## document_consistency_detector (rapidocr + QR cross-check) -- n=680, supersedes the paddlevl n=120 run

- OCR backend: rapidocr (PP-OCR ONNX via onnxruntime-gpu), Colab T4
- Decision threshold: 0.25 (calibrated via best_f1_threshold, applied unchanged)
- Precision: 0.9375
- Recall: 1.0000
- F1: 0.9677
- ROC-AUC: 0.9327
- PR-AUC: 0.9635
- False positive rate: 0.1600 (32 of 200 bonafide invoices)
- n=680 (480 fraud + 200 bonafide); TP=480 FP=32 TN=168 FN=0
- Per split: train recall 1.0000 (n_fraud=240), FPR 0.1910 (n_bonafide=89);
  held_out recall 1.0000 (n_fraud=240), FPR 0.1351 (n_bonafide=111)

Comparison against the superseded incumbent, same detector, same QR logic, different OCR:

| entry | recall | precision | FPR | n |
|---|---|---|---|---|
| rapidocr (this run) | 1.0000 | 0.9375 | 0.1600 | 680 |
| paddlevl (superseded) | 0.9125 | 0.8795 | 0.2500 | 120 |

NOT written by the eval script, and that is the point of this section. The
2026-09-01 Colab run scored all 680 cases and persisted one row per case to
Supabase `evaluation_results`, but its `metrics.json` never reached the repo --
only the notebook's A3 cell printed the result as prose. So `metrics.json`, the
`model_registry` table and the site's Model Performance page all kept reporting
the superseded paddlevl n=120 numbers, including a 25.0% false-positive rate
that a measured 16.0% had already replaced.

Every figure above is recomputed from those persisted per-case rows (run_id
`0ee2574a-1136-48e8-a45c-ea00f649d6db` = train,
`b605a39b-4c31-4096-8df8-4623a8e8d398` = held_out), which carry the real score
and ground truth for each case -- not retyped from the prose. The
recomputation reproduces A3's printed claims exactly, which is the only reason
they are trusted here. The score is quantized to {0, .25, .5, .75, 1.0} by
construction (mismatched-over-comparable across four fields), so ROC-AUC and
PR-AUC are computed over those five levels with ties counted at 0.5.

16% is still high for production. Reported as measured, not as solved.

## voice_spoof_detector -- three-model bake-off, n=204, winner promoted

Identical 204 cases (120 spoof + 84 bonafide), thresholds calibrated the same
way for each: best_f1_threshold on bonafide + train-split spoof only, then
applied unchanged to held_out.

| model | recall | precision | FPR | ROC-AUC | held_out recall |
|---|---|---|---|---|---|
| **mo-thecreator/Deepfake-audio-detection** | **0.9500** | **0.9661** | **0.0476** | **0.9836** | **0.9667** |
| garystafford/wav2vec2-deepfake-voice-detector (incumbent) | 0.8500 | 0.9107 | 0.1190 | 0.9251 | 0.9333 |
| Hemgg/Deepfake-audio-detection | did not load | | | | |

The challenger wins on every axis, and the false-positive rate matters most
here: 4 legitimate clips flagged instead of 10, on the same 84 bonafide files.
That is real customer friction more than halved. Promoted to
`voice_spoof_detector`; the incumbent is kept at
`voice_spoof_detector_garystafford_superseded`.

A challenger that fails to load is a real answer about that checkpoint, not a
gap in the bake-off.

PROVENANCE, because this entry was not written by the eval script: the Colab
run had no GITHUB_TOKEN, so its `metrics.json` never reached the repo -- only
the checkpoint cell's printed output did. The confusion matrix here is
recomputed from the persisted per-case rows (`69916bd3` = train, `a1d2bbc8` =
held_out): TP=114 FP=4 TN=80 FN=6. The 84 bonafide are the shared negative
baseline and are scored in BOTH splits, which is why 288 rows are 204 distinct
cases -- counting them twice would have inflated n and halved the FPR. That
recomputation reproduces the printed precision, recall, f1, FPR and both split
recalls exactly. ROC-AUC and PR-AUC are carried from the same run's output
(they need the continuous scores, which the persisted rows do not hold); every
field around them reconciled, which is the only reason they are trusted.
