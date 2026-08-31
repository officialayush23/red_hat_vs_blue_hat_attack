"""
Deterministic phishing/scam message text generator for the phishing_scam
family (docs/TECHNICAL_SPEC.md Section 4a: "Scam SMS/email/WhatsApp
message," mutation dimensions urgency level, impersonation target,
language). Per Principle 3/4 (extended to every attack artifact, not just
transaction rows): the LLM never authors attack content directly -- this
is template + seeded-random-choice code, same discipline as
scam_script_gen.py (voice_scam's text generator, which this mirrors) and
transaction_gen.py's synthetic transactions.

channel ("sms" | "email") maps directly onto difraud/difraud's own two
relevant domains ("sms" and "phishing", i.e. email) -- deliberate, so the
classifier trained on real difraud data (train_phishing_classifier.py) is
being evaluated against generated artifacts shaped like the same two
channels it learned from, not a third channel it's never seen.

language ("english" | "hinglish") is a held-out-only evasion dimension:
code-mixed Hindi/English phishing text is a real, documented pattern for
bypassing English-only keyword/classifier filters in Indian fraud -- a
genuine "novel... designed to read as legitimate" case per Section 4a,
not an invented difficulty knob.
"""

import random

IMPERSONATION_TARGETS = (
    "bank_otp", "delivery", "tax_refund", "tech_support",  # training-allowed
    "employer_hr", "lottery_prize",  # held-out-only (novel targets)
)
CHANNELS = ("sms", "email")
LANGUAGES = ("english", "hinglish")

_EMAIL_SUBJECTS = {
    "bank_otp": ["Urgent: Verify your account activity", "Security Alert: Unusual login detected"],
    "delivery": ["Delivery Failed - Action Required", "Your package could not be delivered"],
    "tax_refund": ["Income Tax Refund Pending", "You have a pending tax refund of ₹4,850"],
    "tech_support": ["Your device has been compromised", "Immediate action required: Virus detected"],
    "employer_hr": ["Updated HR Policy - Please Review", "Payroll verification for this cycle"],
    "lottery_prize": ["Congratulations! You've been selected", "Claim your prize before it expires"],
}

_BODIES_HIGH_URGENCY = {
    "bank_otp": [
        "We detected unusual activity on your account. Verify immediately by sharing the OTP sent to your registered number, or your account will be blocked within 24 hours.",
        "Your account access will be suspended today unless you confirm your identity. Reply with the 6-digit code you just received.",
    ],
    "delivery": [
        "Your parcel is held at the facility due to an unpaid customs fee of ₹49. Pay now within 2 hours or the package will be returned to sender.",
        "Delivery attempt failed. Click the link and confirm your address within 3 hours to avoid your order being cancelled.",
    ],
    "tax_refund": [
        "Your refund of ₹4,850 will be forfeited if not claimed within 24 hours. Verify your bank details immediately via the secure link.",
        "Final notice: your pending refund expires today. Submit your PAN and bank account number now to receive it.",
    ],
    "tech_support": [
        "Critical security threat detected on your device. Call our support line immediately or your data will be permanently lost.",
        "Your device is sending spam to your contacts right now. Download the fix tool immediately to stop it.",
    ],
    "employer_hr": [
        "Payroll processing is on hold pending your immediate confirmation. Complete the form within the hour or your salary will be delayed.",
        "Your employee benefits enrollment closes today. Confirm your details now to avoid losing coverage.",
    ],
    "lottery_prize": [
        "Your prize of ₹2,50,000 expires in 1 hour! Claim now by sharing your account details to receive the transfer.",
        "Final call: respond within 30 minutes with your UPI ID or the prize will be reassigned to another winner.",
    ],
}

_BODIES_LOW_URGENCY = {
    "bank_otp": [
        "As part of our routine account review, please confirm your recent activity whenever convenient using the link below.",
        "We're updating our verification records. No rush at all, just confirm your details sometime this week.",
    ],
    "delivery": [
        "A small customs fee is pending on a recent order. Settle it at your convenience to release the package.",
        "We tried delivering your order. No hurry, reschedule anytime using the link.",
    ],
    "tax_refund": [
        "A refund has been processed to your name. Whenever you get a chance, verify your bank details to receive it.",
        "Your refund request is in queue. Feel free to complete the verification form whenever suits you.",
    ],
    "tech_support": [
        "Our routine scan found a minor issue on your device. You can address it whenever convenient using the attached tool.",
        "A software update is recommended for your device. No urgency, install it at your leisure.",
    ],
    "employer_hr": [
        "As part of this quarter's routine review, please confirm your details in the HR portal whenever you have a moment.",
        "A minor update to your benefits enrollment is available. Take a look whenever convenient, no deadline.",
    ],
    "lottery_prize": [
        "You've been entered into our loyalty rewards draw and have a small prize waiting. Claim whenever convenient.",
        "A small reward is available under your name. No expiry, claim it whenever you like.",
    ],
}

_HINGLISH_BODIES = {
    "lottery_prize": [
        "Aapka naam ₹2,50,000 ke prize ke liye select hua hai! Jaldi apna UPI ID bhejo warna prize expire ho jayega.",
        "Congratulations! Aapko ek special reward mila hai. Bas apna account detail confirm kar do, koi hurry nahi hai.",
    ],
    "bank_otp": [
        "Aapke account mein suspicious activity dekha gaya hai. Turant OTP share karo warna account block ho jayega.",
    ],
}

_SENDER_NAMES = {
    "bank_otp": ["SecureBank Alerts", "+91-98XXX-XXXXX"],
    "delivery": ["FastShip Logistics", "+91-97XXX-XXXXX"],
    "tax_refund": ["Income Tax Dept (noreply)", "+91-96XXX-XXXXX"],
    "tech_support": ["Windows Defender Alert", "+91-95XXX-XXXXX"],
    "employer_hr": ["HR Department", "+91-94XXX-XXXXX"],
    "lottery_prize": ["Prize Committee", "+91-93XXX-XXXXX"],
}

# Added 2026-08-30 alongside defend/text_features.py's URL features: real
# phishing overwhelmingly drives the victim to a link (credential harvest
# or "pay now" page). Our generated messages had NO url field at all until
# now, so "URL features" had nothing to compute on -- this fixes that.
# Deliberately look-alike-suspicious (hyphenated, off-brand TLD) for the
# high-urgency/credential-harvesting templates -- the actual phishing
# tactic being simulated -- and a URL-shortener style for SMS (real
# smishing overwhelmingly uses shortened links to hide the destination).
_URLS_BY_TARGET = {
    "bank_otp": "http://secure-bankverify-alerts.info/confirm",
    "delivery": "http://fastship-track.co/pay",
    "tax_refund": "http://incometax-refund-status.info/claim",
    "tech_support": "http://windows-defender-alert.top/fix",
    "employer_hr": "http://hr-portal-verify.online/confirm",
    "lottery_prize": "http://prize-claim-now.xyz/claim",
}
_SMS_SHORTLINK = "bit.ly/3xVerifyNow"
# Bonafide links are the negative control: same surface feature (a URL is
# present) but on a plain, non-hyphenated, common-TLD domain -- so the
# model has to learn "suspicious URL shape", not "any URL at all = fraud."
_BONAFIDE_URLS = ["https://app.yourbank.com/dashboard", "https://mail.yourbank.com/unsubscribe"]


def _greeting(customer_name: str | None, rng: random.Random) -> str:
    if customer_name:
        return rng.choice([f"Dear {customer_name},", f"Hi {customer_name},", f"{customer_name},"])
    return rng.choice(["Dear Customer,", "Hello,", ""])


def generate_phishing_message(
    impersonation_target: str, urgency: str, channel: str, rng: random.Random,
    language: str = "english", customer_name: str | None = None,
) -> dict:
    """Deterministic given (impersonation_target, urgency, channel, language,
    rng-state) -- same inputs, same output, no external calls. Returns
    {"channel", "sender", "subject" (email only), "body"}."""
    if impersonation_target not in IMPERSONATION_TARGETS:
        raise KeyError(f"Unknown impersonation_target: {impersonation_target!r}. Known: {IMPERSONATION_TARGETS}")
    if channel not in CHANNELS:
        raise KeyError(f"Unknown channel: {channel!r}. Known: {CHANNELS}")
    if language not in LANGUAGES:
        raise KeyError(f"Unknown language: {language!r}. Known: {LANGUAGES}")

    sender = rng.choice(_SENDER_NAMES[impersonation_target])
    greeting = _greeting(customer_name, rng)

    if language == "hinglish" and impersonation_target in _HINGLISH_BODIES:
        body_bank = _HINGLISH_BODIES[impersonation_target]
    else:
        body_bank = _BODIES_HIGH_URGENCY[impersonation_target] if urgency == "high" else _BODIES_LOW_URGENCY[impersonation_target]
    body_line = rng.choice(body_bank)
    body = f"{greeting} {body_line}".strip()

    url = None
    if urgency == "high":
        url = _SMS_SHORTLINK if channel == "sms" else _URLS_BY_TARGET[impersonation_target]
        body = f"{body} {url}"

    result = {"channel": channel, "sender": sender, "body": body}
    if url:
        result["url"] = url
    if channel == "email":
        result["subject"] = rng.choice(_EMAIL_SUBJECTS[impersonation_target])
    return result


# Expanded 2026-08-30 after a real evidence-gate finding (backend/_diag_phishing_fp.py):
# the original 5-template bank was too thin AND too topically close to
# difraud's bank_otp-style phishing text ("account", "payment", "activity"
# vocabulary overlap) -- every template below now explicitly states there is
# nothing to click/verify/confirm, and the bank covers more everyday,
# non-banking-adjacent notification types so lexical overlap with phishing
# training text isn't concentrated in just two or three templates.
_BONAFIDE_SUBJECTS = [
    "Your order has shipped", "Statement ready for review", "Appointment reminder",
    "Thank you for your payment", "Your monthly summary", "Subscription renewal notice",
    "Delivery address updated", "Welcome aboard", "This week's newsletter",
    "Support ticket resolved", "Loyalty points updated", "Password changed confirmation",
]
_BONAFIDE_BODIES = [
    "Your recent order has shipped and is expected to arrive within 3-5 business days. This is an automatic notification -- no action is needed on your part.",
    "Your latest account statement is now available in your app whenever you'd like to review it. There is nothing to confirm or approve.",
    "This is a friendly reminder for your appointment scheduled next week. Reply only if you'd like to reschedule -- no response needed otherwise.",
    "Thank you -- your payment was processed successfully and a receipt has been filed in your account history for your records.",
    "For your records only: here is a routine summary of last month's account activity. No response or login is required.",
    "Your subscription renewal is scheduled for next month at the same rate as before. You don't need to do anything.",
    "Thanks for updating your delivery address. Future orders will now ship to the new address automatically.",
    "Welcome aboard! Your onboarding checklist is now complete and your account is fully set up.",
    "Here's this week's newsletter with product updates and tips. Unsubscribe anytime from the link in the footer.",
    "Your recent support ticket has been marked resolved. Let us know if you need anything else, otherwise no action is needed.",
    "Your loyalty points balance was updated after your last purchase. Check the app whenever you like to see the new total.",
    "This confirms your account settings were updated successfully. If this was you, no action is needed.",
]


def generate_bonafide_message(channel: str, rng: random.Random, customer_name: str | None = None) -> dict:
    """Self-generated legitimate-looking message, deterministic given
    (channel, rng-state) -- mirrors document_gen.generate_bonafide_documents()
    / librispeech_bonafide.py's role as the negative-class baseline for the
    evidence-gate eval, kept separate from difraud's own non-deceptive rows
    so the classifier's training data and evaluation data don't overlap."""
    if channel not in CHANNELS:
        raise KeyError(f"Unknown channel: {channel!r}. Known: {CHANNELS}")
    greeting = _greeting(customer_name, rng)
    body = f"{greeting} {rng.choice(_BONAFIDE_BODIES)}".strip()
    url = None
    if rng.random() < 0.3:  # a real minority of legitimate notifications do include a link -- negative control for the URL features
        url = rng.choice(_BONAFIDE_URLS)
        body = f"{body} {url}"
    result = {"channel": channel, "sender": "Your Bank", "body": body}
    if url:
        result["url"] = url
    if channel == "email":
        result["subject"] = rng.choice(_BONAFIDE_SUBJECTS)
    return result
