"""
Invoice + QR generation and tampering for the document_fraud family
(Section 4a) -- renders a realistic synthetic TAX INVOICE (GSTIN, address,
line-items table, CGST/SGST breakdown, bank payment details) whose PRINTED
text and embedded QR code encode the same four fields (invoice_number,
beneficiary, amount, bank_account) by default, and can independently
mismatch any of them per the mutation dimensions in
evaluation/split_policy.py's document_fraud entry.

Rewritten 2026-08-30 from the original minimal template (a handful of
lines on a mostly-blank page) to a realistic multi-section invoice --
Mastercard's "fidelity of attacks in simulation" judging criterion is
explicit about this, and a bare template genuinely undersold what the
tampering logic underneath was already doing. The tampering MECHANISM is
unchanged (a field is either edited in the printed text, or the QR payload
is swapped wholesale) -- what changed is that the surrounding document now
looks like an actual invoice a real person would receive, so a single
tampered field reads as "partial editing of an otherwise-real document"
rather than "obviously synthetic form with one field changed."

Five tamperable dimensions total now (was three): amount, beneficiary,
invoice_number, bank_account (2026-08-30 addition -- payment-redirection /
"bank-account replacement" fraud, a real documented pattern), and
qr_payload (the QR itself swapped for a different well-formed invoice's
payload -- "QR-swap fraud"). All five surface as the same observable
(printed value != QR-decoded value) that
defend/pretrained/document_consistency_detector.py checks for.

Customer Universe wiring (2026-08-30, Section 4b-i): when a `customer_name`
/ `trusted_beneficiaries` pair is supplied (see generate_document_attacks.py,
which loads the synthetic_customers roster), a non-beneficiary-tampered
invoice's seller is drawn from THAT customer's own known/trusted vendors
instead of a purely random name, and the "Bill To" block names the actual
customer -- this is what makes "beneficiary tampered" mean something
concrete (a payment redirected away from a vendor this customer actually
trusts) rather than scoring an artifact with no identity context at all.

No external invoice dataset is used or needed here, unlike voice_scam's
LibriSpeech bonafide -- the "ground truth" is whatever this generator
itself put in the QR code, so both the fraud (mismatched) and bonafide
(fully consistent) classes for evaluation/eval_document_consistency.py come
from this same function, just with an empty tamper_dims set for bonafide.

No real identity data anywhere: GSTIN/account-number/IFSC values are
random strings shaped like those fields for visual realism only -- they
are not derived from, and don't collide in format with, real Aadhaar/PAN
numbers, and no real company, bank, or person is named.

Usage:
    from generate.artifact_generators.document_gen import generate_invoice
    result = generate_invoice(
        tamper_dims={"amount"}, rng=rng, out_path="case_0001.png",
        customer_name="Priya Mehta", trusted_beneficiaries=["Meridian Supply Co."],
    )
"""

import json
import random
from pathlib import Path

BENEFICIARY_NAMES = [
    "Meridian Supply Co.", "Northgate Logistics Ltd.", "Aravalli Traders",
    "Blue Harbor Imports", "Silverline Facilities", "Kestrel & Sons",
    "Coral Bay Distributors", "Ashford Manufacturing", "Vantage Point LLC",
    "Riverside Wholesale Group",
]

GOODS_DESCRIPTIONS = [
    "Office Supplies - Bulk Order", "IT Equipment Maintenance", "Consulting Services - Q3",
    "Logistics & Freight Charges", "Software License Renewal", "Facility Maintenance Contract",
    "Raw Material Supply", "Marketing Services Retainer", "Warehouse Storage Fees",
    "Annual Support Contract",
]
STREET_TYPES = ["Industrial Rd", "Commerce St", "Trade Ave", "Business Park Rd", "Enterprise Blvd"]
CITIES = ["Whitfield", "Rosemont", "Kestrel Falls", "Brackenridge", "Fairhaven", "Millbrook"]
BANK_NAMES = ["Meridian National Bank", "Coastal Trust Bank", "Unity Commercial Bank", "Highland Cooperative Bank"]

IMG_SIZE = (1050, 1400)
QR_BOX_SIZE = 180


def _random_base_fields(rng: random.Random) -> dict:
    seller = rng.choice(BENEFICIARY_NAMES)
    n_items = rng.randint(2, 4)
    items = []
    for _ in range(n_items):
        desc = rng.choice(GOODS_DESCRIPTIONS)
        qty = rng.randint(1, 20)
        rate = round(rng.uniform(50.0, 2500.0), 2)
        items.append({"description": desc, "qty": qty, "rate": rate, "amount": round(qty * rate, 2)})
    subtotal = round(sum(i["amount"] for i in items), 2)
    cgst = round(subtotal * 0.09, 2)
    sgst = round(subtotal * 0.09, 2)
    total = round(subtotal + cgst + sgst, 2)
    return {
        "invoice_number": f"INV-{rng.randint(10_000_000, 99_999_999)}",
        "beneficiary": seller,
        "gstin": _random_gstin(rng),
        "seller_address": f"{rng.randint(1, 999)} {rng.choice(STREET_TYPES)}, {rng.choice(CITIES)}",
        "items": items,
        "subtotal": subtotal,
        "cgst": cgst,
        "sgst": sgst,
        "amount": total,  # canonical grand-total field name the detector keys on
        "bank_name": rng.choice(BANK_NAMES),
        "bank_account": _random_account_number(rng),
        "ifsc": _random_ifsc(rng),
    }


def _random_gstin(rng: random.Random) -> str:
    """Visually GSTIN-shaped (state code + 10 alphanumeric + entity + Z +
    checksum char) but purely random -- not derived from or resembling any
    real registered GSTIN. Flavor text only, not compared by the detector."""
    state = rng.choice(["07", "27", "29", "33", "36", "19", "24"])
    body = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(10))
    return f"{state}{body}1Z{rng.choice('123456789')}"


def _random_account_number(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(12))


def _random_ifsc(rng: random.Random) -> str:
    bank_code = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(4))
    return f"{bank_code}0{rng.randint(100000, 999999)}"


def _mutate_field(field: str, current, rng: random.Random):
    """Returns a value guaranteed different from `current`."""
    if field == "amount":
        factor = rng.choice([rng.uniform(0.3, 0.85), rng.uniform(1.15, 3.0)])
        return round(current * factor, 2)
    if field == "beneficiary":
        choices = [b for b in BENEFICIARY_NAMES if b != current]
        return rng.choice(choices)
    if field == "invoice_number":
        new = current
        while new == current:
            new = f"INV-{rng.randint(10_000_000, 99_999_999)}"
        return new
    if field == "bank_account":
        new = current
        while new == current:
            new = _random_account_number(rng)
        return new
    raise ValueError(f"Unknown field: {field}")


def _load_font(size: int, bold: bool = False):
    """Best-effort truetype font for OCR-friendlier rendering; falls back
    to PIL's built-in bitmap font (always available, no external file
    needed) if none of these paths exist on this machine -- OCR accuracy
    on the fallback font is expected to be worse, and that's an honest,
    acceptable outcome to record, not something to hide."""
    from PIL import ImageFont

    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _render_invoice_image(printed: dict, customer_name: str, out_path: Path) -> None:
    from PIL import Image, ImageDraw
    import qrcode

    img = Image.new("RGB", IMG_SIZE, "white")
    draw = ImageDraw.Draw(img)

    title_font = _load_font(30, bold=True)
    header_font = _load_font(20, bold=True)
    body_font = _load_font(18)
    small_font = _load_font(15)

    left_x, right_x = 50, 620
    y = 40

    draw.text((left_x, y), printed["beneficiary"], fill="black", font=title_font)
    draw.text((left_x, y + 38), "TAX INVOICE", fill="black", font=header_font)
    draw.text((left_x, y + 68), printed["seller_address"], fill="black", font=small_font)
    draw.text((left_x, y + 90), f"GSTIN: {printed['gstin']}", fill="black", font=small_font)

    draw.text((right_x, y), f"Invoice #: {printed['invoice_number']}", fill="black", font=body_font)
    draw.text((right_x, y + 28), f"Date: {printed['date']}", fill="black", font=body_font)
    draw.text((right_x, y + 56), f"Due Date: {printed['due_date']}", fill="black", font=body_font)

    y += 140
    draw.line([(left_x, y), (IMG_SIZE[0] - 50, y)], fill="black", width=2)
    y += 25

    draw.text((left_x, y), "Bill To:", fill="black", font=header_font)
    y += 26
    draw.text((left_x, y), customer_name, fill="black", font=body_font)
    y += 45

    col_x = [left_x, left_x + 480, left_x + 620, left_x + 760]
    headers = ["Description", "Qty", "Rate", "Amount"]
    for cx, h in zip(col_x, headers):
        draw.text((cx, y), h, fill="black", font=header_font)
    y += 26
    draw.line([(left_x, y), (IMG_SIZE[0] - 50, y)], fill="black", width=1)
    y += 10
    for item in printed["items"]:
        draw.text((col_x[0], y), item["description"], fill="black", font=body_font)
        draw.text((col_x[1], y), str(item["qty"]), fill="black", font=body_font)
        draw.text((col_x[2], y), f"{item['rate']:.2f}", fill="black", font=body_font)
        draw.text((col_x[3], y), f"{item['amount']:.2f}", fill="black", font=body_font)
        y += 30
    draw.line([(left_x, y), (IMG_SIZE[0] - 50, y)], fill="black", width=1)
    y += 20

    totals_x = left_x + 620
    draw.text((totals_x, y), f"Subtotal: {printed['subtotal']:.2f}", fill="black", font=body_font)
    y += 26
    draw.text((totals_x, y), f"CGST (9%): {printed['cgst']:.2f}", fill="black", font=body_font)
    y += 26
    draw.text((totals_x, y), f"SGST (9%): {printed['sgst']:.2f}", fill="black", font=body_font)
    y += 30
    draw.text((totals_x, y), f"GRAND TOTAL: {printed['amount']:.2f}", fill="black", font=header_font)
    y += 55

    draw.line([(left_x, y), (IMG_SIZE[0] - 50, y)], fill="black", width=2)
    y += 25

    draw.text((left_x, y), "Payment Details", fill="black", font=header_font)
    y += 28
    draw.text((left_x, y), f"Payable to: {printed['beneficiary']}", fill="black", font=body_font)
    y += 26
    draw.text((left_x, y), f"Bank: {printed['bank_name']}", fill="black", font=body_font)
    y += 26
    draw.text((left_x, y), f"A/C No.: {printed['bank_account']}", fill="black", font=body_font)
    y += 26
    draw.text((left_x, y), f"IFSC: {printed['ifsc']}", fill="black", font=body_font)
    y += 45

    qr_payload = printed["_qr"]
    qr_img = qrcode.make(json.dumps(qr_payload)).resize((QR_BOX_SIZE, QR_BOX_SIZE))
    img.paste(qr_img.convert("RGB"), (left_x, y))
    draw.text((left_x, y + QR_BOX_SIZE + 8), "Scan to Pay", fill="black", font=small_font)

    draw.text((totals_x, y + QR_BOX_SIZE - 30), "Authorized Signatory", fill="black", font=small_font)
    draw.line([(totals_x, y + QR_BOX_SIZE - 40), (totals_x + 250, y + QR_BOX_SIZE - 40)], fill="black", width=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def generate_invoice(tamper_dims: set, rng: random.Random, out_path,
                      customer_name: str | None = None,
                      trusted_beneficiaries: list | None = None) -> dict:
    """Generates one invoice image at out_path and returns the ground-truth
    dict describing it: {"printed": {...}, "qr_payload": {...},
    "tampered_fields": [...]} -- tampered_fields is [] for a fully
    consistent (bonafide) document, i.e. tamper_dims == set().

    customer_name / trusted_beneficiaries (Section 4b-i, optional): when
    given, a non-beneficiary-tampered document's seller is drawn from this
    customer's own trusted vendor list rather than any random name, and the
    Bill To block names them -- this is the Customer Universe linkage.
    """
    out_path = Path(out_path)
    base = _random_base_fields(rng)
    base["date"] = f"2026-{rng.randint(1, 8):02d}-{rng.randint(1, 28):02d}"
    base["due_date"] = f"2026-{rng.randint(9, 12):02d}-{rng.randint(1, 28):02d}"

    if trusted_beneficiaries and "beneficiary" not in tamper_dims:
        base["beneficiary"] = rng.choice(trusted_beneficiaries)

    printed = dict(base)
    qr_payload = {k: base[k] for k in ("invoice_number", "beneficiary", "amount", "bank_account")}

    if "qr_payload" in tamper_dims:
        swapped = _random_base_fields(rng)
        qr_payload = {k: swapped[k] for k in ("invoice_number", "beneficiary", "amount", "bank_account")}

    for field in ("amount", "beneficiary", "invoice_number", "bank_account"):
        if field in tamper_dims:
            printed[field] = _mutate_field(field, base[field], rng)

    printed_for_render = dict(printed)
    printed_for_render["_qr"] = qr_payload
    _render_invoice_image(printed_for_render, customer_name or "Valued Customer", out_path)

    return {
        "printed": printed,
        "qr_payload": qr_payload,
        "tampered_fields": sorted(tamper_dims),
        "image_path": str(out_path),
    }


def generate_bonafide_documents(out_dir, n: int, seed: int = 42) -> list:
    """Generates n fully-consistent (untampered) invoices as the negative
    / bonafide class for eval_document_consistency.py -- analogous to
    librispeech_bonafide.fetch_bonafide_clips, but self-generated rather
    than sourced externally. Idempotent -- skips images already on disk."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    existing = sorted(out_dir.glob("document_bonafide_*.png"))
    if len(existing) >= n:
        return existing[:n]

    paths = list(existing)
    for i in range(len(existing), n):
        out_path = out_dir / f"document_bonafide_{i:03d}.png"
        generate_invoice(tamper_dims=set(), rng=rng, out_path=out_path)
        paths.append(out_path)
    return paths
