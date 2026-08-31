"""
Task #35 -- the real LLM strategist (Phase 4, docs/TECHNICAL_SPEC.md),
slotting into the exact seam evaluation/adaptive_weakness_round.py and
generate/mutation_engine.py already reserved for it:

  mutation_engine.py's own module docstring: "an LLM strategist (Phase 4,
  not yet built) may eventually pick WHICH combination to target, but this
  file is what turns a combination into actual numbers" -- that boundary
  is unchanged here. This module ONLY picks a qualitative combination
  (e.g. {"amount": "mid", "velocity": "moderate", ...}). It never touches
  numeric ranges -- turning a combination into concrete transaction values
  stays 100% deterministic, mutation_engine.resolve_params()'s job alone.

  docs/AGENTIC_CONTRACT.md Section 1 already defines the exact input/output
  JSON shape a strategist must produce (written before this file existed,
  specifically so this slots in without a redesign) -- this module's
  return values map directly onto that shape's combination/reasons/
  recommended_action/severity fields.

Principle 9 (must degrade gracefully): propose_next_combination_llm()
returns None on ANY failure -- no API key, package not installed, network
error, malformed JSON, a combination that fails real validation. It never
raises. The caller (adaptive_weakness_round.py) falls back to the
existing rule-based propose_next_combination() exactly as it did before
this file existed. A broken, slow, or absent LLM must never take the
adaptive loop down -- it can only make one round smarter when it works.

Validation, not blind trust: an LLM-proposed combination is accepted only
if (a) the response is valid JSON with every required key in the right
shape, (b) every proposed dimension name is a real dimension for this
family (checked against mutation_engine.DEFAULT_PARAMS[family], the
actual source of truth, not a hand-copied enum that could drift), and
(c) generate/mutation_engine.py's own resolve_params() -- the real
downstream consumer -- runs on it without raising. If any check fails,
this returns None like any other failure; nothing invalid ever reaches
the case generators.

Usage:
    from evaluation.llm_strategist import propose_next_combination_llm
    result = propose_next_combination_llm(family, current_combo, weakness, already_tried)
    if result is not None:
        new_combo, reasons, recommended_action, severity = result
    # else: caller falls back to the rule-based heuristic
"""

import json
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

from generate.mutation_engine import DEFAULT_PARAMS, load_reference_stats, resolve_params  # noqa: E402

_SYSTEM_PROMPT = """You are the adaptive red-team strategist for FraudShield, a fraud-detection evaluation system. Your job: given a fraud-detection model's real measured weakness on one attack family, propose ONE new qualitative attack combination designed to test a genuinely harder variant -- a real adversarial hypothesis grounded in the recall number and current combination, not an arbitrary change.

Rules:
- Only set dimensions that appear in "valid_dimensions_for_this_family". Never invent a new dimension name.
- Boolean dimensions must be JSON true/false, not the strings "true"/"false".
- Prefer a combination not already present in "already_tried_combinations".
- Ground your reasoning in what the recall number and current combination imply the model is (or isn't) keying on.
- Respond with ONLY a single JSON object -- no markdown code fences, no prose outside the JSON -- matching exactly this shape:
{"combination": {"<dimension>": "<value or true/false>", ...}, "reasons": ["...", "..."], "recommended_action": "...", "severity": "low"|"medium"|"high"}"""


def _build_user_prompt(family: str, current_combo: dict, weakness: dict, already_tried: list) -> str:
    dims = sorted(DEFAULT_PARAMS[family].keys())
    return json.dumps({
        "attack_family": family,
        "valid_dimensions_for_this_family": dims,
        "current_combination": current_combo,
        "weakest_model": weakness["model"],
        "measured_recall": weakness["recall"],
        "already_tried_combinations": already_tried,
    }, indent=2)


# gemini-2.0-flash was retired -- confirmed via a real 404 from both the SDK
# and REST paths on 2026-08-31, with Google's own error message naming this
# replacement directly ("This model models/gemini-2.0-flash is no longer
# available... use models/gemini-3.6-flash").
_GEMINI_MODEL = "gemini-3.6-flash"
_GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"


def _call_gemini_sdk(system_prompt: str, user_prompt: str, api_key: str):
    """google-genai -- the current official SDK (google-generativeai is
    deprecated). Much lighter than the deprecated SDK's dependency chain
    (no grpc/protobuf/google-api-python-client), but this project has
    already hit one real Windows pip failure this session on an
    adjacent dependency chain, so this is still wrapped and allowed to
    fail into the REST fallback below rather than trusted blindly."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                response_mime_type="application/json",
            ),
        )
        return resp.text
    except Exception:
        return None


def _call_gemini_rest(system_prompt: str, user_prompt: str, api_key: str):
    """Direct REST fallback, zero extra dependencies -- `requests` is
    already installed project-wide. Used if the SDK isn't installed or
    its call fails for any reason, so one broken dependency chain can't
    take the whole strategist down."""
    try:
        import requests
    except ImportError:
        return None
    try:
        resp = requests.post(
            _GEMINI_URL,
            params={"key": api_key},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


def _call_gemini(system_prompt: str, user_prompt: str):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    return (_call_gemini_sdk(system_prompt, user_prompt, api_key)
            or _call_gemini_rest(system_prompt, user_prompt, api_key))


_stats_cache = None


def _validation_stats() -> dict:
    global _stats_cache
    if _stats_cache is None:
        _stats_cache = load_reference_stats()
    return _stats_cache


def propose_next_combination_llm(family: str, current_combo: dict, weakness: dict, already_tried: list):
    """Returns (new_combo, reasons, recommended_action, severity) on a
    validated success, or None on any failure -- see module docstring."""
    if family not in DEFAULT_PARAMS:
        return None

    user_prompt = _build_user_prompt(family, current_combo, weakness, already_tried)
    raw = _call_gemini(_SYSTEM_PROMPT, user_prompt)
    if raw is None:
        return None

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None

    combo = parsed.get("combination")
    reasons = parsed.get("reasons")
    recommended_action = parsed.get("recommended_action")
    severity = parsed.get("severity")

    if not isinstance(combo, dict) or not combo:
        return None
    if not isinstance(reasons, list) or not reasons or not all(isinstance(r, str) and r for r in reasons):
        return None
    if not isinstance(recommended_action, str) or not recommended_action:
        return None
    if severity not in ("low", "medium", "high"):
        return None

    valid_dims = set(DEFAULT_PARAMS[family].keys())
    if not set(combo.keys()) <= valid_dims:
        return None

    # Real validator: the actual downstream consumer, not a hand-copied
    # enum. A combo that resolve_params() can't handle is genuinely
    # unusable regardless of how well-formed its JSON is.
    try:
        stats = _validation_stats()
        source_dataset = next(iter(stats.keys()))
        resolve_params(family, combo, source_dataset, stats)
    except Exception:
        return None

    return combo, reasons, recommended_action, severity
