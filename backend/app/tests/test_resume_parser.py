"""The `ResumeParser` contract, tested at the seam rather than through HTTP.

This is seam 2 from the spec design. It exists so the parser's contract is pinned
independently of the route that calls it — the identifiers asserted here are what
`provenance_map` references in ADR 0006, and they have no other test to protect them.
"""

import pytest

from app.adapters.resume_parser import (
    ResumeParseFailed,
    ResumeUnreadable,
    get_resume_parser,
)
from app.tests.fixtures.pdf_bytes import MINIMAL_PDF, RECORDED_RESUME_PDF


def _parser():  # type: ignore[no-untyped-def]
    return get_resume_parser()


async def test_parsing_returns_a_structured_resume() -> None:
    parsed = await _parser().parse(RECORDED_RESUME_PDF)

    assert parsed.experience
    assert parsed.skills


async def test_every_experience_entry_has_an_identifier() -> None:
    parsed = await _parser().parse(RECORDED_RESUME_PDF)

    ids = [entry.id for entry in parsed.experience]
    assert all(ids)
    assert len(set(ids)) == len(ids)


async def test_every_bullet_has_an_identifier() -> None:
    """Without these, `provenance_map` has nothing to point at.

    ADR 0006 makes a tailored bullet traceable to its source. That reference is a
    bullet id, so ids are a hard requirement of parsing rather than a convenience.
    """
    parsed = await _parser().parse(RECORDED_RESUME_PDF)

    bullet_ids = [bullet.id for entry in parsed.experience for bullet in entry.bullets]
    assert bullet_ids
    assert all(bullet_ids)
    assert len(set(bullet_ids)) == len(bullet_ids)


async def test_identifiers_are_stable_across_parses() -> None:
    """The same document must produce the same ids.

    A provenance map stored against one parse has to still resolve after the resume is
    read again, or every saved tailoring silently loses its evidence.
    """
    first = await _parser().parse(RECORDED_RESUME_PDF)
    second = await _parser().parse(RECORDED_RESUME_PDF)

    def bullet_ids(parsed: object) -> list[str]:
        return [b.id for e in parsed.experience for b in e.bullets]  # type: ignore[attr-defined]

    assert bullet_ids(first) == bullet_ids(second)


async def test_the_full_text_is_retained() -> None:
    """The validator draws its entity set from the whole document.

    A skill mentioned only in a summary line must not read as fabricated when it
    appears in a tailored bullet, so the validator needs more than the bullets.
    """
    parsed = await _parser().parse(RECORDED_RESUME_PDF)

    assert parsed.raw_text
    first_bullet = parsed.experience[0].bullets[0].text
    assert first_bullet[:40] in parsed.raw_text


async def test_dates_are_kept_exactly_as_written() -> None:
    """Never normalised, never inferred.

    A real resume mixes `January 2026 - Present` with `Aug 2023` in one document.
    Turning either into a structured range invents precision the document does not
    contain, which is the failure ADR 0006 exists to prevent.
    """
    parsed = await _parser().parse(RECORDED_RESUME_PDF)

    written = [entry.dates for entry in parsed.experience]
    assert "January 2026 - Present" in written


async def test_a_wrapped_bullet_is_one_bullet() -> None:
    """From spike 002: continuation lines carry no marker.

    A parser splitting on lines would cut long bullets in half and promote the tail to
    a bullet of its own. The validator would then reject faithful rewrites of exactly
    the longest, most detailed bullets — the ones most worth tailoring.

    Asserted as a join rather than a length threshold: the point is that text from both
    physical lines ends up in one bullet, which a length check only implies.
    """
    parsed = await _parser().parse(RECORDED_RESUME_PDF)

    bullets = [b.text for e in parsed.experience for b in e.bullets]
    joined = [text for text in bullets if "stream records instead of" in text]

    assert len(joined) == 1, "the head of the wrapped bullet should appear exactly once"
    assert "cutting peak memory use" in joined[0], "the continuation line was not joined"
    assert not any(
        text.startswith("buffering them") for text in bullets
    ), "the continuation was promoted to a bullet of its own"


async def test_nothing_parsed_is_absent_from_the_source_text() -> None:
    """The parse-time version of ADR 0006.

    Structuring is the one step where a language model reads the resume, and its job is
    recall — catching a skill listed in an unusual place. The same freedom lets it add:
    inventing a skill, or promoting "familiar with Docker" to "Docker".

    A fabrication here is worse than a missed skill, because everything downstream
    trusts the parsed resume. Scoring would match on a skill the student does not have,
    tailoring would assert it to an employer, and the gap list would omit it as already
    held. Nothing would surface the error.

    So the contract is checkable rather than trusted: every skill must appear in the
    source text. Asserted now, before ticket 06 introduces the model that makes it
    possible to violate.
    """
    parsed = await _parser().parse(RECORDED_RESUME_PDF)
    haystack = parsed.raw_text.casefold()

    for skill in parsed.skills:
        assert skill.casefold() in haystack, f"parsed skill absent from source: {skill}"


async def test_no_employer_or_title_is_absent_from_the_source_text() -> None:
    parsed = await _parser().parse(RECORDED_RESUME_PDF)
    haystack = parsed.raw_text.casefold()

    for entry in parsed.experience:
        assert entry.employer.casefold() in haystack
        assert entry.title.casefold() in haystack


async def test_a_pdf_with_no_text_layer_is_reported_as_unreadable() -> None:
    """Distinct from a parse failure, because the student's fix is different.

    A scanned resume needs re-exporting as text. A structuring failure is not
    something the student can act on at all.
    """
    with pytest.raises(ResumeUnreadable):
        await _parser().parse(MINIMAL_PDF)


async def test_unreadable_and_parse_failed_are_different_types() -> None:
    assert not issubclass(ResumeUnreadable, ResumeParseFailed)
    assert not issubclass(ResumeParseFailed, ResumeUnreadable)


async def test_failure_is_never_signalled_by_an_empty_result() -> None:
    """An empty resume and a failed parse are different facts.

    Returning an empty result for a failure means the student is shown a resume with
    nothing in it and no explanation, and the caller cannot tell the two apart.
    """
    with pytest.raises(ResumeUnreadable):
        await _parser().parse(MINIMAL_PDF)
