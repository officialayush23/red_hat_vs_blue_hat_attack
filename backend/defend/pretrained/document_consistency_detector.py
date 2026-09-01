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

QR decoding uses OpenCV's built-in cv2.QRCodeDetector. That used to arrive
as a transitive dependency of paddleocr; now that the OCR engine is
selectable and paddle is no longer required, opencv-python is a dependency
of this detector in its own right and is listed as one in
requirements.txt. rapidocr-onnxruntime pulls it in too, but relying on
that would put the QR half of this detector at the mercy of whichever OCR
backend happens to be installed.

Identity-consistency-vs-customer-profile (does the beneficiary match this
case's customer_id's trusted_beneficiaries?) is deliberately NOT built
into this class -- it needs no model and no evidence gate (it's a plain
dict lookup against generate/synthetic_customers.py's roster), so it
belongs in the API layer (Task #36) that already has the case's
customer_id in hand, not duplicated here.
"""

import json
import os
import re
from difflib import SequenceMatcher
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


# ---------------------------------------------------------------------------
# OCR backends
# ---------------------------------------------------------------------------
#
# 2026-09-01: the OCR engine is now pluggable, because PaddleOCR-VL turned
# out to be the single most fragile dependency in this project and the
# least necessary one.
#
# What it cost:
#   - Windows local inference: [WinError 127] from the paddle/torch bundled
#     cudnn filename collision, then os error 1455 (pagefile) at first
#     inference after a full successful model load.
#   - CPU inference measured at 373.5 s/image -- 480 cases would be ~50 h.
#   - Colab: `EVAL FAILED: A dependency error occurred during pipeline
#     creation` even after installing paddlepaddle + paddleocr, with
#     paddle reporting GPU: False.
#
# What it was buying: reading four printed fields off invoices THIS PROJECT
# RENDERS ITSELF with Pillow (generate/artifact_generators/document_gen.py)
# -- clean, high-contrast, known-font, axis-aligned text. A 0.9B-parameter
# document-parsing VLM is not needed to read a rendered invoice; it was
# chosen for layout robustness on real-world scans, which these are not.
#
# Everything downstream of OCR here (the four regexes, the QR cross-check,
# the scoring) only ever consumed one joined text string, so the engine was
# always swappable -- it just wasn't swappable *at runtime*.
#
# Backends, in the order auto-detection tries them:
#   rapidocr  -- the PP-OCR models themselves, run through onnxruntime.
#                Same recognition lineage as paddle's, no paddlepaddle, no
#                CUDA DLLs, no pagefile blow-up; installs and runs on
#                Windows. This is why the whole document evaluation can go
#                back to running locally.
#   tesseract -- pytesseract + the tesseract binary. Excellent on clean
#                rendered text, tiny, but needs a system package.
#   easyocr   -- torch-based, GPU if present.
#   paddlevl  -- the original PaddleOCR-VL path, unchanged, still selectable.
#
# Override with DOC_OCR_BACKEND=rapidocr|tesseract|easyocr|paddlevl.
#
# IMPORTANT for evidence-gating: changing the engine changes the detector.
# The recorded document_consistency_detector numbers (recall 0.9125,
# precision 0.8795, n=120) were measured with paddlevl. Any run on another
# backend must be recorded as its own entry -- score_with_evidence()
# reports the backend in its evidence so a result can never be read as if
# it came from a different engine.

_BACKEND_ORDER = ("rapidocr", "tesseract", "easyocr", "paddlevl")


class _RapidOCRBackend:
    name = "rapidocr"

    # rapidocr-onnxruntime runs the PP-OCR ONNX graphs through onnxruntime,
    # so "GPU" here is entirely a question of which onnxruntime EXECUTION
    # PROVIDER is registered -- not of different weights. The det/cls/rec
    # graphs, their thresholds and their post-processing are byte-identical
    # either way; CUDA only changes where the matmuls run. That is why a
    # CUDA run is NOT recorded as a separate backend entry: it is the same
    # detector, faster.
    #
    # The plain `pip install rapidocr-onnxruntime` pulls CPU onnxruntime,
    # which is why the 680-image bake-off ran at CPU speed on Colab. To get
    # CUDA you must install `onnxruntime-gpu` and ASK for it -- RapidOCR
    # defaults every stage to CPU regardless of what is installed.
    #
    # DOC_OCR_USE_GPU=auto (default) uses CUDA when the provider is actually
    # registered, and silently stays on CPU when it is not, so the same code
    # path runs on a Windows laptop and on a Colab T4. =1 forces CUDA and
    # raises if it is unavailable (so a "GPU run" that quietly fell back to
    # CPU can't be mistaken for a fast one); =0 forces CPU.

    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR

        want = os.environ.get("DOC_OCR_USE_GPU", "auto").strip().lower()
        available = False
        try:
            import onnxruntime
            available = "CUDAExecutionProvider" in onnxruntime.get_available_providers()
        except Exception:
            available = False

        if want in ("1", "true", "yes"):
            if not available:
                raise RuntimeError(
                    "DOC_OCR_USE_GPU=1 but onnxruntime has no CUDAExecutionProvider. "
                    "Install onnxruntime-gpu (and remove the CPU onnxruntime wheel -- "
                    "the two conflict), or set DOC_OCR_USE_GPU=auto to run on CPU."
                )
            use_cuda = True
        elif want in ("0", "false", "no"):
            use_cuda = False
        else:
            use_cuda = available

        self.use_cuda = use_cuda
        if use_cuda:
            self._engine = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
        else:
            self._engine = RapidOCR()

    def read(self, image_path: str) -> str:
        result, _ = self._engine(str(image_path))
        if not result:
            return ""
        # RapidOCR returns [[box, text, confidence], ...] in reading order.
        return "\n".join(str(line[1]) for line in result)


class _TesseractBackend:
    name = "tesseract"

    def __init__(self):
        import pytesseract
        from PIL import Image
        self._pytesseract = pytesseract
        self._Image = Image
        # Fails here rather than on the first image if the binary is absent.
        pytesseract.get_tesseract_version()

    def read(self, image_path: str) -> str:
        return self._pytesseract.image_to_string(self._Image.open(str(image_path)))


class _EasyOCRBackend:
    name = "easyocr"

    def __init__(self):
        import easyocr
        self._reader = easyocr.Reader(["en"], verbose=False)

    def read(self, image_path: str) -> str:
        return "\n".join(self._reader.readtext(str(image_path), detail=0))


class _PaddleVLBackend:
    name = "paddlevl"

    def __init__(self):
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

    def read(self, image_path: str) -> str:
        results = self._ocr.predict(str(image_path))
        return "\n".join(self._markdown_text(res) for res in results)


_BACKENDS = {
    "rapidocr": _RapidOCRBackend,
    "tesseract": _TesseractBackend,
    "easyocr": _EasyOCRBackend,
    "paddlevl": _PaddleVLBackend,
}


def _load_backend():
    """Explicit choice if DOC_OCR_BACKEND is set, otherwise the first
    backend in _BACKEND_ORDER that actually imports and initialises.
    Raises with every failure listed, rather than a bare ImportError for
    whichever one happened to be tried last."""
    requested = os.environ.get("DOC_OCR_BACKEND", "").strip().lower()
    if requested:
        if requested not in _BACKENDS:
            raise ValueError(f"DOC_OCR_BACKEND={requested!r} is not one of {sorted(_BACKENDS)}")
        return _BACKENDS[requested]()

    failures = []
    for name in _BACKEND_ORDER:
        try:
            return _BACKENDS[name]()
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    raise RuntimeError(
        "No OCR backend available for the document-consistency detector. Tried:\n  "
        + "\n  ".join(failures)
        + "\n\nInstall one of:\n"
        "  pip install rapidocr-onnxruntime      (recommended -- runs on Windows, CPU, no paddle)\n"
        "  pip install pytesseract               (plus the tesseract binary)\n"
        "  pip install easyocr\n"
        "  pip install 'paddleocr[doc-parser]' paddlepaddle-gpu"
    )


class DocumentConsistencyDetector:
    """Lazy-loads an OCR backend on first use (not at import time) so
    importing this module needs no OCR dependency at all unless the
    detector is actually used. See the backend notes above for why the
    engine is selectable rather than hardcoded to PaddleOCR-VL."""

    def __init__(self, backend=None):
        self._ocr = None
        self._backend = backend

    @property
    def backend_name(self) -> str:
        self._ensure_loaded()
        return self._ocr.name

    def _ensure_loaded(self) -> None:
        if self._ocr is not None:
            return
        self._ocr = _BACKENDS[self._backend]() if self._backend else _load_backend()

    def _extract_printed_fields(self, image_path: str) -> dict:
        self._ensure_loaded()
        joined = self._ocr.read(image_path)

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

    # Characters OCR genuinely confuses on rendered text. Folding these before
    # comparison turns "a character was misrecognised" into a match, while
    # leaving "this is a different name/account entirely" a mismatch.
    _OCR_FOLD = str.maketrans({
        "O": "0", "o": "0", "D": "0", "Q": "0",
        "I": "1", "l": "1", "|": "1",
        "S": "5", "B": "8", "Z": "2", "G": "6",
    })

    @staticmethod
    def _norm_text(value) -> str:
        """Case, whitespace and punctuation folded. OCR emits 'ACME  Corp.'
        for 'ACME Corp' often enough that an exact string comparison is
        measuring the OCR engine, not the document."""
        t = str(value).strip().lower()
        t = re.sub(r"[^\w\s]", "", t)
        return re.sub(r"\s+", " ", t)

    @classmethod
    def _values_match(cls, key: str, printed_val, qr_val) -> bool:
        """Is the printed value the SAME VALUE as the QR's, allowing for OCR
        noise but not for substitution?

        Why this is not an exact comparison any more (2026-09-01):

        The document detector's false-positive rate on legitimate invoices was
        23.5% -- 47 of 200 consistent documents flagged as tampered. On a
        consistent invoice every field matches by construction, so every one of
        those was the detector misreading its own generated file.

        The mechanism is arithmetic. score() is mismatched/comparable, and there
        are four comparable fields, so the score is quantised to
        {0, 0.25, 0.5, 0.75, 1.0}. The calibrated threshold sits at 0.25.
        A SINGLE character misread in ONE of four fields therefore produces a
        full mismatch on that field, a score of exactly 0.25, and a flag. One
        bad character in four fields is roughly a one-in-four document -- which
        is the false-positive rate that was measured.

        So: text fields compare on a normalised form, with a similarity ratio
        for the remainder, and identifier fields additionally fold the
        character pairs OCR actually confuses.

        This does NOT weaken tamper detection, and that matters more than the
        FPR. document_gen.py tampers by SUBSTITUTION -- a different beneficiary,
        a different account number, a different amount -- not by perturbing a
        character. A substituted value scores far below the 0.90 similarity
        floor, while an OCR slip scores far above it. The two cases were never
        close together; exact matching just could not tell them apart.
        """
        if key == "amount":
            if qr_val is None:
                return False
            try:
                return abs(float(printed_val) - float(qr_val)) < 0.01
            except (TypeError, ValueError):
                return False

        p_norm, q_norm = cls._norm_text(printed_val), cls._norm_text(qr_val)
        if not q_norm:
            return False
        if p_norm == q_norm:
            return True

        if key in ("bank_account", "invoice_number"):
            # Identifiers are alphanumeric codes with no linguistic
            # redundancy, so a single confused glyph is both likely and
            # invisible. Fold the known confusions and require the folded
            # forms to be identical -- no fuzzy ratio here, because two
            # genuinely different account numbers can be one digit apart.
            if p_norm.translate(cls._OCR_FOLD) == q_norm.translate(cls._OCR_FOLD):
                return True
            return False

        # Names: a similarity floor. 0.90 is comfortably above what an OCR
        # slip costs on a company name and far above what a substituted name
        # scores.
        return SequenceMatcher(None, p_norm, q_norm).ratio() >= 0.90

    def _compare_fields(self, printed: dict, qr: dict) -> list:
        """Shared by score() and score_with_evidence() -- one comparison
        pass, returns a list of (field, printed_val, qr_val, matched) so
        the evidence-viewer wiring (Task #32) can show WHICH field tripped
        the score, not just the number."""
        results = []
        for key in ("invoice_number", "beneficiary", "amount", "bank_account"):
            if key not in printed:
                continue
            results.append((key, printed[key], qr.get(key),
                            self._values_match(key, printed[key], qr.get(key))))
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
        # Which engine read this image is part of the evidence, not a
        # footnote: swapping the OCR backend changes the detector, and a
        # result recorded without it could be compared against numbers from
        # a different engine as though they measured the same thing.
        engine = [f"ocr_backend={self.backend_name}"]
        qr = self._decode_qr(image_path)
        if qr is None:
            # ABSTAIN, do not accuse. An undecodable QR means the reader
            # failed on this image; it is not evidence that the document was
            # tampered with. Returning 1.0 here stated maximal confidence in
            # fraud on the strength of not having read the thing that decides
            # it -- and since the calibrated threshold is 0.25, every such
            # image was counted as a detection. On legitimate invoices that is
            # a pure false positive manufactured by the detector's own
            # failure. 0.5 is the same "genuinely unknown" value already used
            # when OCR finds none of the four fields.
            return 0.5, engine + [
                "QR payload could not be decoded -- score is an abstention, NOT a tamper "
                "finding. The QR is the ground truth this detector compares against; "
                "without it there is nothing to compare."
            ]

        comparisons = self._compare_fields(printed, qr)
        if not comparisons:
            return 0.5, engine + ["OCR found none of the 4 comparable fields -- score is genuinely unknown"]

        evidence = list(engine)
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
