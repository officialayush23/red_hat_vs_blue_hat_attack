"""
One-off diagnostic (not part of the pipeline, delete after use): shows
exactly which bonafide messages the phishing_classifier is flagging as
phishing and why -- real evidence before deciding on a fix, per the
project's evidence-gate research discipline (never guess at a root cause).
"""
import json
import sys
from pathlib import Path

import joblib

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

bundle = joblib.load(BACKEND_DIR / "defend" / "models" / "phishing_classifier.joblib")
vectorizer, model, threshold = bundle["vectorizer"], bundle["model"], bundle["threshold"]

bonafide_dir = REPO_ROOT / "data" / "generated" / "phishing_bonafide"
cases = [json.loads(p.read_text()) for p in sorted(bonafide_dir.glob("*.json"))]

results = []
for c in cases:
    text = f"{c.get('subject', '')}\n{c.get('body', '')}".strip() if c.get("subject") else c.get("body", "")
    score = model.predict_proba(vectorizer.transform([text]))[0, 1]
    results.append((score, c["case_id"], c.get("subject", ""), c["body"][:80]))

results.sort(reverse=True)
n_flagged = sum(1 for s, *_ in results if s >= threshold)
print(f"threshold={threshold:.4f}  {n_flagged}/{len(results)} bonafide messages flagged as phishing\n")
for score, case_id, subject, body in results:
    flag = "FLAGGED " if score >= threshold else "ok      "
    print(f"{flag} score={score:.4f}  {case_id}  subj={subject!r}  body={body!r}")
