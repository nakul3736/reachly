"""Extraction across structurally different resumes.

These exist to make overfitting fail loudly. Spike 002 examined one real resume, produced
by LaTeX; a parser validated only against that is tuned to LaTeX whether or not anyone
intended it, and the tuning is invisible until the first student whose resume came out of
Word.

The variants disagree on heading case, bullet marker, date position, and section order.
See `scripts/make_sample_resume_pdf.py` for the comparison table.
"""

import pytest

from app.adapters.pdf_text import MIN_MEANINGFUL_CHARS, extract_text
from app.tests.fixtures.pdf_bytes import RESUME_VARIANTS


@pytest.mark.parametrize("name", sorted(RESUME_VARIANTS))
def test_every_variant_yields_text(name: str) -> None:
    text = extract_text(RESUME_VARIANTS[name])

    assert len(text) > MIN_MEANINGFUL_CHARS


@pytest.mark.parametrize("name", sorted(RESUME_VARIANTS))
def test_every_variant_retains_its_skills_in_the_text(name: str) -> None:
    """Whatever the layout, the words a student wrote survive extraction.

    This is the floor the structuring step builds on: if a skill is absent from the
    extracted text, no amount of structuring can recover it, and the parse-time
    no-fabrication rule would have to reject it.
    """
    text = extract_text(RESUME_VARIANTS[name]).casefold()

    expected = {
        "latex_like": ["python", "fastapi", "postgresql"],
        "word_like": ["go", "kubernetes", "terraform"],
        "plain": ["ruby", "rails", "rspec"],
    }[name]

    for skill in expected:
        assert skill in text


def test_the_variants_do_not_share_a_layout() -> None:
    """Guards the guard.

    If the variants drifted into looking alike, they would stop testing generality while
    still passing. The whole value of the set is that they disagree.
    """
    texts = {
        name: [line for line in extract_text(data).split("\n") if line.strip()]
        for name, data in RESUME_VARIANTS.items()
    }

    def marked_bullets(lines: list[str]) -> int:
        return sum(1 for line in lines if line.lstrip().startswith(("\u2022", "-")))

    def upper_case_headings(lines: list[str]) -> int:
        return sum(
            1
            for line in lines
            if line.strip() == line.strip().upper() and len(line.strip()) > 3
        )

    assert marked_bullets(texts["latex_like"]) > 0
    assert marked_bullets(texts["plain"]) == 0
    assert upper_case_headings(texts["word_like"]) > 0
    assert upper_case_headings(texts["latex_like"]) == 0
