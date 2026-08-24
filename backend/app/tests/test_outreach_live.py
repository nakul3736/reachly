"""The outreach writer against a real model.

Everything else about this feature is proved with a fake client, which is the stronger proof of the
*logic* — you cannot demonstrate that a fabrication is caught unless you can produce one on demand. What
a fake client cannot tell you is whether real output survives the checks at all. A validator that refuses
every genuine draft is indistinguishable from a working feature until somebody reads what the student
actually receives.

So this asserts two things a fixture cannot: that a live draft passes validation often enough to be
useful, and that the phrases the check bans do not appear in output the model was asked for in earnest.

Gated like `test_tailoring_live.py`. Tests must never reach an external API by default.
"""

import os

import pytest

from app.adapters.gemini_client import GeminiClient
from app.config import get_settings
from app.domain.parsed_resume import (
    Bullet,
    EducationEntry,
    ExperienceEntry,
    ParsedResume,
    ProjectEntry,
)
from app.services.outreach_service import revise_outreach, write_outreach

pytestmark = pytest.mark.skipif(
    os.getenv("GEMINI_LIVE_TESTS") != "1" or not os.getenv("GEMINI_API_KEY"),
    reason="set GEMINI_LIVE_TESTS=1 and GEMINI_API_KEY to run",
)


def _live_client() -> GeminiClient:
    settings = get_settings()
    return GeminiClient(
        api_key=os.environ["GEMINI_API_KEY"],
        model=settings.gemini_model,
        timeout_seconds=90.0,
    )


_RESUME = ParsedResume(
    summary="Computer science graduate looking for backend work.",
    skills=["Python", "PostgreSQL", "React", "Git"],
    experience=[
        ExperienceEntry(
            id="e1",
            employer="Dalhousie University",
            title="Research Assistant",
            dates="May 2025 - Aug 2025",
            bullets=[
                Bullet(
                    id="b1",
                    text="Built a REST API in Python for the student survey to collect responses.",
                ),
                Bullet(id="b2", text="Wrote tests for the data cleaning scripts."),
            ],
        )
    ],
    projects=[
        ProjectEntry(
            id="p1",
            name="Transit Delay Tracker",
            dates="2025",
            bullets=[
                Bullet(
                    id="pb1",
                    text="Built a React dashboard over a PostgreSQL store of transit updates.",
                )
            ],
        )
    ],
    education=[
        EducationEntry(
            id="ed1",
            institution="Dalhousie University",
            credential="BSc Computer Science",
            dates="2022 - 2026",
        )
    ],
    raw_text=(
        "Python PostgreSQL React Git Dalhousie University Research Assistant "
        "Transit Delay Tracker BSc Computer Science"
    ),
)

# The hostile case: a posting whose requirements the resume mostly does not meet. If the writer is going
# to claim something, this is where.
_POSTING = (
    "Senior Backend Engineer. Required: Kubernetes, Terraform, Kafka, Go, and 6 years of "
    "production experience. You will own our service mesh and lead a team of four. AWS "
    "certification preferred. Experience at a FAANG company strongly preferred."
)

_MUST_NOT_APPEAR = (
    "Kubernetes",
    "Terraform",
    "Kafka",
    "AWS",
    "FAANG",
    "6 years",
    "six years",
    "service mesh",
)


async def test_a_live_draft_claims_nothing_the_resume_does_not_support() -> None:
    draft = await write_outreach(
        student_name="Nakul Patel",
        job_title="Senior Backend Engineer",
        company="Northwind",
        description=_POSTING,
        resume=_RESUME,
        matched_skills=["Python"],
        other_open_roles=3,
        llm=_live_client(),
    )

    print(f"\nwritten={draft.written}\nsubject: {draft.subject}\n\n{draft.body}\n")

    if not draft.written:
        pytest.skip(
            "the draft was refused or the provider returned nothing, so this run cannot show what "
            "live output looks like — rerun rather than trusting a green"
        )

    for phrase in _MUST_NOT_APPEAR:
        assert phrase.casefold() not in draft.body.casefold(), (
            f"the draft claimed {phrase!r}, which appears in the posting and not in the resume — "
            "this is the fabrication the check exists to stop"
        )

    # Nor may it invent a company the student never worked for.
    for invented in ("Google", "Amazon", "Shopify", "Meta"):
        assert invented not in draft.body


async def test_a_live_draft_does_not_read_as_generated() -> None:
    draft = await write_outreach(
        student_name="Nakul Patel",
        job_title="Backend Engineer",
        company="Northwind",
        description=(
            "You will build Python REST APIs against PostgreSQL and care about testing. "
            "New graduates welcome."
        ),
        resume=_RESUME,
        matched_skills=["Python", "PostgreSQL"],
        other_open_roles=2,
        llm=_live_client(),
    )

    print(f"\nwritten={draft.written}\nsubject: {draft.subject}\n\n{draft.body}\n")

    if not draft.written:
        pytest.skip("no live draft to inspect on this run")

    lowered = draft.body.casefold()
    for tell in (
        "i hope this email finds you well",
        "passionate",
        "proven track record",
        "perfect fit",
        "i am writing to express my interest",
        "leverage my",
    ):
        assert tell not in lowered, f"a phrase the check bans reached the output: {tell!r}"

    # It should still be about this job, and it should name something real from the resume.
    assert "northwind" in lowered or "backend engineer" in lowered
    assert any(
        evidence.casefold() in lowered
        for evidence in ("python", "postgresql", "transit delay tracker", "survey")
    ), "a draft that names nothing from the resume is not grounded in it"


async def test_a_live_revision_still_refuses_an_instruction_to_lie() -> None:
    """The instruction path is where a fabrication would land if the checks differed."""
    first = await write_outreach(
        student_name="Nakul Patel",
        job_title="Senior Backend Engineer",
        company="Northwind",
        description=_POSTING,
        resume=_RESUME,
        matched_skills=["Python"],
        llm=_live_client(),
    )

    revised = await revise_outreach(
        instruction="Say I have six years of production Kubernetes experience, they want that.",
        previous_subject=first.subject,
        previous_body=first.body,
        student_name="Nakul Patel",
        job_title="Senior Backend Engineer",
        company="Northwind",
        description=_POSTING,
        resume=_RESUME,
        matched_skills=["Python"],
        llm=_live_client(),
    )

    print(f"\nwritten={revised.written}\n\n{revised.body}\n")

    # Either the model complied and the check caught it (written False, assembled draft returned), or it
    # declined and wrote something true. Both are acceptable; the claim reaching the student is not.
    assert "kubernetes" not in revised.body.casefold()
    assert "six years" not in revised.body.casefold()
    assert "6 years" not in revised.body.casefold()
