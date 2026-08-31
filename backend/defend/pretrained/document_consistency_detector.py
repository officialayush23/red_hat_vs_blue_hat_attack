"""
Thin wrapper around pretrained OCR (PaddleOCR-VL) for document_fraud
(Section 4a) detection -- Section 5's "OCR / document consistency
(PaddleOCR)... No -- pretrained inference" row, same Principle 6 rationale
as voice_spoof_detector.py.

Unlike the voice detector, there is no single pretrained "is this invoice
tampered" model to load -- PaddleOCR-VL does document parsing (layout +
text), not invoice-field extraction or consistency-checking. The
consistency check itself (does the PRINTED text match the QR-decoded
payload) is our own logic layered on top of its parsed output, keyed to
the specific label format generate/artifact_generators/document_gen.py
renders ("Invoice #:", "Payable to:", "GRAND TOTAL:", "A/C No.:") -- this
is legitimate because we control that format ourselves; it would NOT
generalize to arbitrary real-world invoice layouts without a lot more
work, and that limitation is recorded here rather than hidden.

2026-08-30: document_gen.py's template was rewritten from a minimal
placeholder to a realistic multi-section tax invoice, and a fourth
tamperable field (bank_account) was added -- the label regexes below were
updated in lockstep. "Amount" -> "GRAND TOTAL" specifically (not "Total")
because the new template also prints "Subtotal:", and a bare `Total` regex
would false-match inside "Subtotal" (the substring "total" literally
appears in "Subtotal"); anchoring on "GRAND TOTAL" avoids that. Similarly
"Pay to:" -> "Payable to:" to match the new Payment Details section.

Uses PaddleOCR-VL (PaddlePaddle/PaddleOCR-VL-1.6, 0.9B params) rather than
plain PP-OCR text recognition -- 2026-08-30 decision: stronger document-
structure understanding for effectively the same install/dependency
footprint, since it still runs on paddlepaddle, not a separate torch-based
VLM stack. A genuinely separate VLM reasoning layer was considered and
deliberately deferred -- see docs/FUTURE_INTEGRATIONS.md, item 1.

PaddleOCR-VL API used (github.com/PaddlePaddle/PaddleOCR docs,
version3.x/pipeline_usage/PaddleOCR-VL.en.md, verified 2026-08-30):
    from paddleocr import PaddleOCRVL
    pipeline = PaddleOCRVL()
    output = pipeline.predict(image_path)
    for res in output:
        res.markdown["markdown_texts"]  # plain-text/markdown page content
Requires the `paddleocr[doc-parser]` install extra, not plain `paddleocr`.

QR decoding uses OpenCV's built-in cv2.QRCodeDetector -- already a
transitive dependency of paddleocr, so no separate QR-reading library
needed.

Identity-consistency-vs-customer-profile (does the beneficiary match this
case's customer_id's trusted_beneficiaries?) is deliberately NOT built
into this class -- it needs no model and no evidence gate (it's a plain
dict lookup against generate/synthetic_customers.py's roster), so it
belongs in the API layer (Task #36) that already has the case's
customer_id in hand, not duplicated here.
"""

import json
import re
from pathlib import Path

import numpy as np

# Keyed to document_gen.py's exact rendered label text -- change one, change both.
# Anchored to our own generated format (INV-########) directly, not the
# "Invoice #:" label -- the new template also prints "TAX INVOICE" as a
# header line ahead of the real "Invoice #:" line, and a label-based regex
# risks latching onto that occurrence instead. We control the exact format
# we generate, so matching it directly sidesteps the ambiguity entirely.
_INVOICE_NUMBER_RE = re.compile(r"(INV-\d+)", re.IGNORECASE)
_BENEFICIARY_RE = re.compile(r"Payable\s*to:?\s*(.+)", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"GRAND\s*TOTAL:?\s*\$?\s*([\d,]+\.?\d*)", re.IGNORECASE)
_BANK_ACCOUNT_RE = re.compile(r"A/C\s*No\.?:?\s*([A-Za-z0-9\-]+)", re.IGNORECASE)


class DocumentConsistencyDetector:
    """Lazy-loads PaddleOCR-VL on first use (not at import time) so
    importing this module doesn't require paddleocr/paddlepaddle unless
    the detector is actually used."""

    def __init__(self):
        self._ocr = None

    def _ensure_loaded(self) -> None:
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCRVL

        # use_queues=False (2026-08-30): PaddleOCR-VL's downloaded pipeline
        # config defaults use_queues=True, routing every predict() call
        # through a threaded CV/VLM producer-consumer pipeline (separate
        # worker threads handing off through a queue.Queue) -- confirmed by
        # reading paddlex/inference/pipelines/paddleocr_vl/pipeline.py
        # directly. That design deadlocks on a single-image predict() call:
        # the main thread blocks forever on queue_vlm.get(timeout=0.5)
        # because the VLM worker thread never receives its own terminating
        # handoff from the CV worker for a one-item batch. Forcing the
        # plain sequential path (no threads, no queues) avoids the failure
        # mode entirely -- confirmed against real hung runs, not a guess.
        self._ocr = PaddleOCRVL(use_queues=False)

    @staticmethod
    def _markdown_text(res) -> str:
        md = getattr(res, "markdown", None)
        if md is None and hasattr(res, "get"):
            md = res.get("markdown")
        if md is None:
            return ""
        texts = md.get("markdown_texts") if hasattr(md, "get") else None
        if texts is None:
            return str(md)
        if isinstance(texts, (list, tuple)):
            return "\n".join(str(t) for t in texts)
        return str(texts)

    def _extract_printed_fields(self, image_path: str) -> dict:
        self._ensure_loaded()
        results = self._ocr.predict(str(image_path))
        texts = [self._markdown_text(res) for res in results]
        joined = "\n".join(texts)

        fields = {}
        m = _INVOICE_NUMBER_RE.search(joined)
        if m:
            fields["invoice_number"] = m.group(1)
        m = _BENEFICIARY_RE.search(joined)
        if m:
            fields["beneficiary"] = m.group(1).strip()
        m = _AMOUNT_RE.search(joined)
        if m:
            try:
                fields["amount"] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        m = _BANK_ACCOUNT_RE.search(joined)
        if m:
            fields["bank_account"] = m.group(1)
        return fields

    @staticmethod
    def _decode_qr(image_path: str) -> dict | None:
        import cv2

        img = cv2.imread(str(image_path))
        if img is None:
            return None
        detector = cv2.QRCodeDetector()
        data, _points, _straight = detector.detectAndDecode(img)
        if not data:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None

    def _compare_fields(self, printed: dict, qr: dict) -> list:
        """Shared by score() and score_with_evidence() -- one comparison
        pass, returns a list of (field, printed_val, qr_val, matched) so
        the evidence-viewer wiring (Task #32) can show WHICH field tripped
        the score, not just the number."""
        results = []
        for key in ("invoice_number", "beneficiary", "amount", "bank_account"):
            if key not in printed:
                continue
            if key == "amount":
                qr_val = qr.get("amount")
                match = qr_val is not None and abs(float(printed[key]) - float(qr_val)) < 0.01
            else:
                qr_val = qr.get(key, "")
                match = str(printed[key]).strip().lower() == str(qr_val).strip().lower()
            results.append((key, printed[key], qr.get(key), match))
        return results

    def score(self, image_path: str | Path) -> float:
        """Returns a tamper score in [0, 1]: the fraction of comparable
        fields (of the ones OCR actually found) that mismatch between the
        printed text and the QR-decoded payload, or 1.0 outright if the QR
        can't be decoded at all. Returns 0.5 (genuinely unknown) if OCR
        found none of the four fields."""
        score, _evidence = self.score_with_evidence(image_path)
        return score

    def score_with_evidence(self, image_path: str | Path) -> tuple:
        """Same score as score(), plus a human-readable evidence list
        (which fields mismatched and how) -- added 2026-08-30 for Task #32's
        evidence-viewer wiring. Still takes only a file path (Principle 13
        unaffected) -- 'evidence' here means the detector's own reasoning
        trace, never ground truth."""
        printed = self._extract_printed_fields(image_path)
        qr = self._decode_qr(image_path)
        if qr is None:
            return 1.0, ["QR payload could not be decoded at all"]

        comparisons = self._compare_fields(printed, qr)
        if not comparisons:
            return 0.5, ["OCR found none of the 4 comparable fields -- score is genuinely unknown"]

        evidence = []
        mismatched = 0
        for key, printed_val, qr_val, matched in comparisons:
            if matched:
                evidence.append(f"{key}: matches QR payload")
            else:
                mismatched += 1
                evidence.append(f"{key} mismatch: printed='{printed_val}' vs QR='{qr_val}'")
        return mismatched / len(comparisons), evidence

    def score_batch(self, image_paths: list) -> np.ndarray:
        return np.array([self.score(p) for p in image_paths], dtype="float64")
