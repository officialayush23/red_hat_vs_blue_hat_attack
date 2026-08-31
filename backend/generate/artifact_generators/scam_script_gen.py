"""
Deterministic scam-script text generator for the voice_scam family
(docs/TECHNICAL_SPEC.md Section 4a). Per Principle 3/4 (extended in spirit
to every attack artifact, not just transaction rows): the LLM never
authors attack content directly -- this is template + seeded-random-choice
code, same discipline as transaction_gen.py's synthetic transactions.

Each script_type maps to a small bank of phrase variants; urgency and
target framing pick which variant fires. voice_characteristics ("cloned_customer"
vs unset/generic) doesn't change the TEXT -- it's resolved by
mutation_engine.py into which audio-generation path voice_gen.py takes
(plain TTS vs. XTTS-v2 cloning against a synthetic customer's registered
reference voice, Section 4b-i). Keeping that split here (text) vs. there
(audio path) means this module has zero GPU/audio dependencies -- it's
pure string templating, testable without touching a model.
"""

import random

SCRIPT_TYPES = ("bank_manager_verification", "kyc_reverification", "family_emergency")

_OPENERS = {
    "bank_manager_verification": [
        "Hello, this is {agent_title} calling from the fraud prevention team.",
        "Good {daypart}, I'm calling on behalf of your bank's security department.",
    ],
    "kyc_reverification": [
        "Hi, we're reaching out because your KYC verification is due for a routine refresh.",
        "This call is regarding a pending identity re-verification on your account.",
    ],
    "family_emergency": [
        "Hey, it's me -- I know this is a strange number, I lost my phone.",
        "It's me, don't panic, I'm okay, but I need your help with something urgent.",
    ],
}

_URGENCY_LINES = {
    "high": [
        "We've flagged unusual activity and need to verify your identity immediately or your account will be temporarily suspended.",
        "This needs to be resolved in the next few minutes to avoid a hold being placed on your funds.",
    ],
    "low": [
        "There's no rush at all, whenever you get a moment would be fine.",
        "It's a small thing, no pressure, just wanted to give you a heads up.",
    ],
}

_ASKS = {
    "bank_manager_verification": [
        "Could you confirm the one-time code that was just sent to your registered number?",
        "For verification, can you read back the last four digits of your card and the OTP you received?",
    ],
    "kyc_reverification": [
        "Could you confirm your date of birth and the OTP on screen so we can complete the refresh?",
        "I'll need you to verify your registered address and the code you just received.",
    ],
    "family_emergency": [
        "Can you send a bit of money to this new account, I'll explain everything later, I promise.",
        "I need you to transfer something small right now, it's an emergency, I'll pay you back.",
    ],
}

_DAYPARTS = ["morning", "afternoon", "evening"]
_AGENT_TITLES = ["Priya from customer protection", "Officer Sharma", "Alex from the verification desk"]


def generate_scam_script(script_type: str, urgency: str, rng: random.Random) -> str:
    """Deterministic given (script_type, urgency, rng-state) -- same inputs,
    same output, no external calls."""
    if script_type not in SCRIPT_TYPES:
        raise KeyError(f"Unknown script_type: {script_type!r}. Known: {SCRIPT_TYPES}")
    if urgency not in _URGENCY_LINES:
        raise KeyError(f"Unknown urgency: {urgency!r}. Known: {list(_URGENCY_LINES)}")

    opener = rng.choice(_OPENERS[script_type]).format(
        agent_title=rng.choice(_AGENT_TITLES),
        daypart=rng.choice(_DAYPARTS),
    )
    urgency_line = rng.choice(_URGENCY_LINES[urgency])
    ask = rng.choice(_ASKS[script_type])
    return f"{opener} {urgency_line} {ask}"
