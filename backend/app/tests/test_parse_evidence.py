"""The guard around the model, tested offline with stub responses.

Full rigour here deliberately. This is the code that decides whether to believe a language
model about someone's work history, and every downstream feature trusts its output. The
live Gemini tests establish that the model reads varied layouts; these establish that a
model behaving badly cannot get anything past us.
"""

from typing import Any

import pytest

from app.adapters.real_resume_parser import RealResumeParser
from app.adapters.resume_parser import ResumeParseFailed
from app.domain.evidence import appears_in, normalise

SOURCE = """Alex Rivera
Skills
Languages: Python, TypeScript
Experience
Software Developer Intern January 2026 - Present
Northwind Analytics
\u2022 Rebuilt the nightly ingestion job to stream records instead of
buffering them, cutting peak memory use by 60 percent.
Education
Dalhousie University
Bachelor of Computer Science, expected 2027"""


class StubLLM:
    """Returns whatever payload a test hands it."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, Any]:
        return self._payload


def _parse(payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Parse `SOURCE` with a stubbed model response, skipping PDF extraction."""
    monkeypatch.setattr(
        "app.adapters.real_resume_parser.extract_text", lambda _: SOURCE
    )
    return RealResumeParser(StubLLM(payload)).parse(b"%PDF-1.4 irrelevant")


_GOOD_ROLE = {
    "employer": "Northwind Analytics",
    "title": "Software Developer Intern",
    "dates": "January 2026 - Present",
    "bullets": [
        "Rebuilt the nightly ingestion job to stream records instead of buffering "
        "them, cutting peak memory use by 60 percent."
    ],
}


# --- the wrapped bullet, which is the case most likely to be got wrong ----------------


def test_a_wrapped_bullet_is_accepted_despite_the_line_break() -> None:
    """The bullet is one line in the response and two in the source.

    Without whitespace normalisation this comparison fails, and it fails specifically for
    long detailed bullets — the ones most worth tailoring. Tested at the primitive because
    it is the single assumption the whole evidence check rests on.
    """
    joined = (
        "Rebuilt the nightly ingestion job to stream records instead of buffering "
        "them, cutting peak memory use by 60 percent."
    )

    assert "\n" in SOURCE
    assert joined not in SOURCE  # a literal comparison would reject it
    assert appears_in(joined, SOURCE)  # normalised, it is found


def test_normalise_collapses_whitespace_and_case() -> None:
    assert normalise("  Two   Words\n") == "two words"


def test_appears_in_rejects_an_empty_claim() -> None:
    """An empty string is a substring of everything, which would wave anything through."""
    assert not appears_in("", SOURCE)
    assert not appears_in("   ", SOURCE)


async def test_a_wrapped_bullet_survives_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = await _parse({"skills": [], "experience": [_GOOD_ROLE]}, monkeypatch)

    bullets = parsed.experience[0].bullets
    assert len(bullets) == 1
    assert "cutting peak memory use" in bullets[0].text


# --- fabrication ----------------------------------------------------------------------


async def test_an_invented_skill_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Additive noise, so removing it leaves the resume correct and less complete.

    Refusing the whole upload over one hallucinated word would be worse for the student
    than dropping the word.
    """
    parsed = await _parse(
        {"skills": ["Python", "Kubernetes"], "experience": [_GOOD_ROLE]}, monkeypatch
    )

    assert parsed.skills == ["Python"]


async def test_an_invented_bullet_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    role = {**_GOOD_ROLE, "bullets": [*_GOOD_ROLE["bullets"], "Led a team of twelve."]}

    parsed = await _parse({"skills": [], "experience": [role]}, monkeypatch)

    texts = [b.text for b in parsed.experience[0].bullets]
    assert "Led a team of twelve." not in texts
    assert len(texts) == 1


async def test_an_invented_employer_fails_the_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """A whole invented role fails rather than being dropped.

    A resume missing a job is something the student notices and questions. A job they
    never had, presented as parsed from their own document, they might believe.
    """
    role = {**_GOOD_ROLE, "employer": "Globex Corporation"}

    with pytest.raises(ResumeParseFailed):
        await _parse({"skills": [], "experience": [role]}, monkeypatch)


async def test_an_invented_title_fails_the_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    role = {**_GOOD_ROLE, "title": "Senior Staff Engineer"}

    with pytest.raises(ResumeParseFailed):
        await _parse({"skills": [], "experience": [role]}, monkeypatch)


async def test_an_invented_date_is_dropped_not_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """A normalised date is an invented one.

    `2026-01` never appears in the document even though `January 2026 - Present` does, so
    it is a claim about precision the resume does not carry.
    """
    role = {**_GOOD_ROLE, "dates": "2026-01 to present"}

    parsed = await _parse({"skills": [], "experience": [role]}, monkeypatch)

    assert parsed.experience[0].dates == ""


async def test_an_invented_summary_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = await _parse(
        {
            "summary": "Highly motivated engineer with a passion for scalable systems.",
            "skills": [],
            "experience": [_GOOD_ROLE],
        },
        monkeypatch,
    )

    assert parsed.summary == ""


# --- malformed and empty responses ----------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"experience": []},
        {"experience": "not a list"},
        {"experience": [{"employer": "", "title": ""}]},
        {"skills": "Python"},
    ],
    ids=["empty", "no-roles", "wrong-type", "blank-role", "skills-not-a-list"],
)
async def test_an_unusable_response_fails_rather_than_returning_nothing(
    payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Text was read, so the document is not blank.

    Returning an empty resume would be a claim about the student's history rather than a
    report about our processing, and the interface could not tell the two apart.
    """
    with pytest.raises(ResumeParseFailed):
        await _parse(payload, monkeypatch)


async def test_duplicate_skills_are_collapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = await _parse(
        {"skills": ["Python", "python", "PYTHON"], "experience": [_GOOD_ROLE]}, monkeypatch
    )

    assert parsed.skills == ["Python"]


# --- identifiers ----------------------------------------------------------------------


async def test_identifiers_are_derived_from_content_not_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An id supplied by the model is ignored.

    Ours are content-derived, so they survive re-parsing. Trusting the model's would mean
    a stored provenance map could stop resolving whenever it felt like numbering
    differently.
    """
    role = {**_GOOD_ROLE, "id": "model-supplied-id"}

    parsed = await _parse({"skills": [], "experience": [role]}, monkeypatch)

    assert parsed.experience[0].id != "model-supplied-id"
    assert len(parsed.experience[0].id) == 16


async def test_the_same_document_yields_the_same_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = await _parse({"skills": [], "experience": [_GOOD_ROLE]}, monkeypatch)
    second = await _parse({"skills": [], "experience": [_GOOD_ROLE]}, monkeypatch)

    assert [e.id for e in first.experience] == [e.id for e in second.experience]
    assert [b.id for b in first.experience[0].bullets] == [
        b.id for b in second.experience[0].bullets
    ]
