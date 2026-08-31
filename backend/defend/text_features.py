"""
Hand-engineered urgency/actionability features for the phishing_classifier
(defend/train/train_phishing_classifier.py, evaluation/eval_phishing_classifier.py).

Added 2026-08-30 after a real evidence-gate finding: plain TF-IDF bag-of-
words alone gave ROC-AUC 0.59 and a 70% false-positive rate scoring our
own generated bonafide messages (backend/_diag_phishing_fp.py output) --
banking-topic vocabulary ("account", "payment", "receipt", "activity") is
shared between ordinary transactional notifications and real difraud
phishing text (much of which impersonates a bank), so a purely lexical
model conflates TOPIC with INTENT. These features are the actual
differentiator: a phishing message pushes urgent, time-boxed,
credential/OTP-harvesting action; a legitimate notification does not.

The feature lexicon below is fixed and generic (imperative CTA verbs,
urgency/deadline phrases, credential-harvesting nouns, threat phrases) --
it was NOT derived by inspecting our own held-out generated cases, so
this doesn't violate Principle 7 (held-out combinations must never inform
training/feature choices). It's ordinary domain-knowledge feature
engineering, applied identically at train time (on real difraud text) and
at evidence-gate score time (on our own generated text) via the single
function below -- both scripts import it from here so train-time and
score-time feature computation can never silently drift apart.
"""

import re

import numpy as np
from scipy import sparse

_URGENCY_PHRASES = (
    "immediately", "urgent", "urgently", "right now", "today", "asap",
    "expire", "expires", "expiring", "expired", "within 24 hours",
    "within hours", "within 1 hour", "within 2 hours", "within 3 hours",
    "final notice", "last chance", "act now", "before it", "hurry",
)
# Explicit LOW-urgency / reassurance cues -- a real difraud phishing message
# essentially never says these (the whole tactic is manufactured urgency),
# so this is a genuine negative signal for the deceptive class, not just
# "absence of urgency." Bonafide notifications say this constantly.
_REASSURANCE_PHRASES = (
    "no rush", "no hurry", "no urgency", "whenever convenient",
    "at your convenience", "no action is needed", "no action needed",
    "nothing to confirm", "nothing requires your attention",
    "for your records", "informational only", "automatic notification",
)
_THREAT_PHRASES = (
    "suspend", "suspended", "block", "blocked", "close your account",
    "restricted", "deactivat", "terminated", "penalty", "forfeit",
    "permanently lost", "reassigned to another",
)
_CREDENTIAL_PHRASES = (
    "otp", "one-time password", "pin", "cvv", "password", "verify your",
    "confirm your identity", "click the link", "click here",
    "share the code", "share your", "bank details", "account number",
    "upi id", "pan card", "aadhaar",
)
_IMPERATIVE_WORDS = ("verify", "click", "confirm", "share", "reply", "download", "call", "claim", "submit", "pay")

# Added 2026-08-30 alongside generate/artifact_generators/phishing_text_gen.py's
# url field: real phishing overwhelmingly drives the victim to a link. A
# bare "has a URL" feature is nearly useless on its own though (legitimate
# notifications have links too, by design in our own bonafide generator --
# a deliberate negative control) -- the actual signal is the URL's SHAPE:
# a hyphenated look-alike domain, an off-brand TLD, or a shortener hiding
# the destination.
_SUSPICIOUS_TLDS = ("info", "xyz", "top", "online")
_URL_PATTERN = re.compile(r"(?:https?://|www\.|bit\.ly/)[^\s]+", re.IGNORECASE)
_DOMAIN_PATTERN = re.compile(r"(?:https?://)?([a-z0-9.-]+\.[a-z]{2,})", re.IGNORECASE)


def _count_hits(text_lower: str, phrases) -> int:
    return sum(1 for p in phrases if p in text_lower)


def _has_currency_with_deadline(text: str, text_lower: str) -> int:
    has_amount = bool(re.search(r"[₹$]\s?[\d,]+", text))
    has_deadline = any(p in text_lower for p in ("hour", "today", "expire", "final", "last chance"))
    return 1 if (has_amount and has_deadline) else 0


def _has_early_imperative(text_lower: str) -> int:
    window = text_lower[:80]
    return 1 if any(re.search(rf"\b{w}\b", window) for w in _IMPERATIVE_WORDS) else 0


def _url_features(text: str) -> tuple:
    """Returns (has_url, uses_shortener, suspicious_tld, hyphenated_domain)."""
    match = _URL_PATTERN.search(text)
    if not match:
        return 0, 0, 0, 0
    url = match.group(0)
    uses_shortener = 1 if "bit.ly" in url.lower() else 0
    domain_match = _DOMAIN_PATTERN.search(url)
    domain = domain_match.group(1).lower() if domain_match else ""
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    suspicious_tld = 1 if tld in _SUSPICIOUS_TLDS else 0
    hyphenated = 1 if "-" in domain else 0
    return 1, uses_shortener, suspicious_tld, hyphenated


FEATURE_NAMES = (
    "urgency_phrase_count", "reassurance_phrase_count", "threat_phrase_count",
    "credential_phrase_count", "currency_with_deadline", "early_imperative_cta",
    "has_url", "url_uses_shortener", "url_suspicious_tld", "url_hyphenated_domain",
)


def build_hand_features(texts: list) -> "sparse.csr_matrix":
    """One row per text, columns per FEATURE_NAMES. Returns a sparse matrix
    so it hstacks directly with a TF-IDF matrix (scipy.sparse.hstack)."""
    rows = []
    for text in texts:
        lower = text.lower()
        has_url, uses_shortener, suspicious_tld, hyphenated = _url_features(text)
        rows.append([
            _count_hits(lower, _URGENCY_PHRASES),
            _count_hits(lower, _REASSURANCE_PHRASES),
            _count_hits(lower, _THREAT_PHRASES),
            _count_hits(lower, _CREDENTIAL_PHRASES),
            _has_currency_with_deadline(text, lower),
            _has_early_imperative(lower),
            has_url, uses_shortener, suspicious_tld, hyphenated,
        ])
    return sparse.csr_matrix(np.array(rows, dtype="float64"))
