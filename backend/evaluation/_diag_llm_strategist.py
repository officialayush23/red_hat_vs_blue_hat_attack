"""
One-off diagnostic (same convention as backend/_diag_phishing_fp.py,
backend/diag_bonafide.py, backend/diag_use_queues.py) -- calls
evaluation/llm_strategist.py's internal SDK and REST paths DIRECTLY and
prints the real exception each one hits, instead of the module's normal
silent-fallback behavior (by design, for the production adaptive loop --
but that means the actual failure reason never reaches stdout). Run this
once from backend/ to see exactly where the call is failing, then delete
it -- not meant to be a permanent file.

Usage:
    python evaluation/_diag_llm_strategist.py
"""

import os
import sys
import traceback
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from evaluation.llm_strategist import _SYSTEM_PROMPT, _build_user_prompt, _GEMINI_MODEL, _GEMINI_URL

api_key = os.environ.get("GEMINI_API_KEY")
print(f"GEMINI_API_KEY present: {bool(api_key)} (length {len(api_key) if api_key else 0})")
print(f"Model: {_GEMINI_MODEL}")
print()

family = "transaction_fraud"
current_combo = {"amount": "mid", "velocity": "moderate", "merchant_category": "new", "time_of_day": "off_hours"}
weakness = {"model": "autoencoder", "attack_family": family, "recall": 0.43}
already_tried = [current_combo]
user_prompt = _build_user_prompt(family, current_combo, weakness, already_tried)

print("=" * 70)
print("STEP 1: google-genai SDK path")
print("=" * 70)
try:
    from google import genai
    from google.genai import types
    print("SDK import: OK")
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                temperature=0.4,
                response_mime_type="application/json",
            ),
        )
        print("SDK call: OK")
        print("Raw response.text:")
        print(repr(resp.text))
    except Exception:
        print("SDK call FAILED with:")
        traceback.print_exc()
except ImportError:
    print("SDK import FAILED (google-genai not installed)")
    traceback.print_exc()

print()
print("=" * 70)
print("STEP 2: direct REST path")
print("=" * 70)
try:
    import requests
    resp = requests.post(
        _GEMINI_URL,
        params={"key": api_key},
        json={
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
        },
        timeout=30,
    )
    print(f"HTTP status: {resp.status_code}")
    print("Body:")
    print(resp.text[:2000])
except Exception:
    print("REST call FAILED with:")
    traceback.print_exc()

print()
print("=" * 70)
print("STEP 3: end-to-end propose_next_combination_llm() with validation")
print("=" * 70)
from evaluation.llm_strategist import propose_next_combination_llm
result = propose_next_combination_llm(family, current_combo, weakness, already_tried)
print("Result:", result)
