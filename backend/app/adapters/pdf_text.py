"""PDF text extraction.

The deterministic half of parsing. Extraction never varies and never involves a model:
pdfplumber either finds a text layer or there is not one. Only *structuring* that text
into roles and bullets is swappable, which is why the two are separate.
"""

import io

import pdfplumber

from app.adapters.resume_parser import ResumeUnreadable

# A PDF can open cleanly, report pages, and contain no text at all — that is exactly
# what a scan looks like. A handful of stray characters from a letterhead is not a
# resume either, so the threshold is above zero.
MIN_MEANINGFUL_CHARS = 40


def extract_text(pdf_bytes: bytes) -> str:
    """The document's text layer.

    Raises `ResumeUnreadable` when there is nothing to read — a scan, an image export,
    or an encrypted file. That is a distinct condition from text that cannot be
    structured, because the student can act on it and cannot act on the other.
    """
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:
        # pdfplumber raises a wide range of types for damaged or encrypted files, and
        # the distinction between them is not one the student can act on.
        raise ResumeUnreadable from exc

    text = "\n".join(pages).strip()
    if len(text) < MIN_MEANINGFUL_CHARS:
        raise ResumeUnreadable
    return text
