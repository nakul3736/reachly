"""Parsing with the real model, against real and varied documents.

**These call Gemini and cost quota.** Skipped unless `GEMINI_LIVE_TESTS=1` and
`GEMINI_API_KEY` are both set, so CI and a fresh clone never invoke them — a test suite
that silently spends someone's API budget is a bad neighbour.

Run them yourself with:

    $env:GEMINI_API_KEY = "..."
    $env:GEMINI_LIVE_TESTS = "1"
    $env:REACHLY_REAL_RESUME_PDF = "C:\\path\\to\\resume.pdf"
    pytest -q app/tests/test_gemini_live.py -rs

This is the only place the model's *generality* can actually be established. Offline tests
pin our validation, identifier derivation and failure handling — all worth having, none of
which say anything about whether the model reads a Word-style layout correctly. Only a real
call does that, which is why these exist despite being slow and skipped by default.
"""

import os

import pytest

from app.adapters.gemini_client import GeminiClient
from app.adapters.real_resume_parser import RealResumeParser
from app.domain.evidence import appears_in
from app.domain.parsed_resume import ParsedResume
from app.tests.fixtures.pdf_bytes import RESUME_VARIANTS

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GEMINI_LIVE_TESTS") == "1" and os.environ.get("GEMINI_API_KEY")),
    reason="set GEMINI_LIVE_TESTS=1 and GEMINI_API_KEY to run tests that call Gemini",
)


def _parser() -> RealResumeParser:
    from app.config import get_settings

    settings = get_settings()
    api_key = os.environ["GEMINI_API_KEY"]
    return RealResumeParser(
        GeminiClient(
            api_key=api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    )


def _assert_nothing_invented(parsed: ParsedResume) -> None:
    """Every claim traces to the source text.

    Asserted on the *result*, so it holds regardless of what the model returned. This is
    the parse-time form of ADR 0006 and the reason the model is allowed near the resume
    at all.
    """
    for skill in parsed.skills:
        assert appears_in(skill, parsed.raw_text), f"invented skill: {skill!r}"
    for entry in parsed.experience:
        assert appears_in(entry.employer, parsed.raw_text), (
            f"invented employer: {entry.employer!r}"
        )
        assert appears_in(entry.title, parsed.raw_text), f"invented title: {entry.title!r}"
        if entry.dates:
            assert appears_in(entry.dates, parsed.raw_text), f"invented dates: {entry.dates!r}"
        for bullet in entry.bullets:
            assert appears_in(bullet.text, parsed.raw_text), f"invented bullet: {bullet.text!r}"


@pytest.mark.parametrize("variant", sorted(RESUME_VARIANTS))
async def test_gemini_parses_every_layout(variant: str) -> None:
    """The generality claim, tested rather than asserted.

    The three variants disagree on heading case, bullet marker, date position and section
    order — see the table in scripts/make_sample_resume_pdf.py. `plain` has no bullet
    markers at all. Passing all three is evidence the model is reading the document
    instead of matching one layout.
    """
    parsed = await _parser().parse(RESUME_VARIANTS[variant])

    assert parsed.experience, f"{variant}: no experience extracted"
    assert parsed.skills, f"{variant}: no skills extracted"
    assert all(entry.bullets for entry in parsed.experience), (
        f"{variant}: a role has no bullets"
    )
    _assert_nothing_invented(parsed)


@pytest.mark.parametrize("variant", sorted(RESUME_VARIANTS))
async def test_gemini_joins_wrapped_bullets(variant: str) -> None:
    """No bullet is a bare continuation fragment.

    Spike 002's finding: continuation lines carry no marker, so a line-based reading
    splits long bullets and promotes the tail. A fragment is recognisable by starting
    lower-case — a copied bullet starts with a capital.
    """
    parsed = await _parser().parse(RESUME_VARIANTS[variant])

    for entry in parsed.experience:
        for bullet in entry.bullets:
            first = bullet.text.lstrip()[:1]
            assert not first.islower(), f"{variant}: looks like a continuation: {bullet.text!r}"


async def test_gemini_parses_a_real_resume(real_resume_pdf: bytes) -> None:
    """The document this was all designed around.

    Structural assertions only — never a name, employer or contact detail. Asserting on
    real personal content would put it in the repository by another route.
    """
    parsed = await _parser().parse(real_resume_pdf)

    assert len(parsed.experience) >= 2, "expected multiple roles in a real resume"
    assert len(parsed.skills) >= 5
    assert sum(len(entry.bullets) for entry in parsed.experience) >= 4
    _assert_nothing_invented(parsed)


async def test_gemini_keeps_real_dates_as_written(real_resume_pdf: bytes) -> None:
    """Mixed formats survive rather than being standardised.

    A real resume carries `January 2026 - Present` beside `Aug 2023`. If every date came
    back in one shape, the model normalised them — which is inventing precision the
    document does not contain.
    """
    parsed = await _parser().parse(real_resume_pdf)

    dates = [entry.dates for entry in parsed.experience if entry.dates]
    assert dates, "expected at least one date"
    for value in dates:
        assert appears_in(value, parsed.raw_text), f"date not as written: {value!r}"


async def test_gemini_is_stable_across_two_calls(real_resume_pdf: bytes) -> None:
    """Temperature zero, so identifiers do not drift.

    Bullet ids are derived from content. If two parses of one document disagreed, stored
    provenance maps would stop resolving and every saved tailoring would lose its
    evidence. Employers and titles are compared rather than every bullet, because this
    has to be a fair test of stability and not of the model's phrasing luck.
    """
    first = await _parser().parse(real_resume_pdf)
    second = await _parser().parse(real_resume_pdf)

    assert [e.id for e in first.experience] == [e.id for e in second.experience]
