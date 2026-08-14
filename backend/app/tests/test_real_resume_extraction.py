"""Extraction against a real resume.

Skipped unless `REACHLY_REAL_RESUME_PDF` points at a resume outside the repository. See
the fixture in `conftest.py` for why the file is not committed.

These assert **structural properties only** — never a name, employer, or contact detail.
A test that asserted on real personal content would put that content in the repository
by another route, which is the thing being avoided.
"""

import re
from itertools import pairwise

from app.adapters.pdf_text import MIN_MEANINGFUL_CHARS, extract_text


def test_a_real_resume_yields_a_text_layer(real_resume_pdf: bytes) -> None:
    text = extract_text(real_resume_pdf)

    assert len(text) > MIN_MEANINGFUL_CHARS * 10


def test_a_real_resume_contains_bullet_markers(real_resume_pdf: bytes) -> None:
    """The marker survives extraction, which is what makes the text-only path viable.

    If a real document produced no recognisable markers, bullet detection would need
    geometry — and spike 002 rejected geometry as format-specific.
    """
    text = extract_text(real_resume_pdf)

    assert "\u2022" in text


def test_a_real_resume_has_bullets_that_wrap_without_a_marker(
    real_resume_pdf: bytes,
) -> None:
    """The spike 002 finding, asserted rather than remembered.

    A bullet line followed by a line with no marker is a wrapped continuation. This is
    the case that a line-based parser gets wrong, so it is worth failing loudly if a
    real document ever stops exhibiting it — that would mean the fixture no longer
    models reality.
    """
    lines = [line for line in extract_text(real_resume_pdf).split("\n") if line.strip()]

    continuations = [
        following
        for current, following in pairwise(lines)
        if current.lstrip().startswith("\u2022") and not following.lstrip().startswith("\u2022")
    ]

    assert continuations, "expected at least one wrapped bullet in a real resume"


def test_a_real_resume_mixes_date_formats(real_resume_pdf: bytes) -> None:
    """Why dates are kept as written.

    Full month names beside abbreviations, and an open end like `Present`. Normalising
    these into ranges means inventing precision the document does not carry.
    """
    text = extract_text(real_resume_pdf)

    assert re.search(r"(19|20)\d\d", text), "expected at least one year"
    assert re.search(r"[Pp]resent|\b[A-Z][a-z]{2}\b\s+(19|20)\d\d", text)


def test_extraction_is_deterministic(real_resume_pdf: bytes) -> None:
    """Same bytes, same text.

    Content-derived bullet ids depend on this. If extraction varied between runs, ids
    would drift and stored provenance maps would stop resolving.
    """
    assert extract_text(real_resume_pdf) == extract_text(real_resume_pdf)
