"""Live, adversarial verification of the tailoring guarantee. Gated, and deliberately cheap.

The offline tests prove the validator rejects fabrication that a scripted fake produces. They
cannot prove the thing the product actually claims: that a *real* model, handed a posting demanding
skills the student does not have, cannot get a fabrication past the check and onto the screen.

So the posting here is hostile on purpose. It asks for Kubernetes, AWS, Terraform, Go and a list of
metrics, against a resume that contains none of them. A model asked to make this resume fit will
reach for exactly those words — which is the behaviour every competing tool ships and calls
tailoring.

Two environment variables rather than one: a configured key alone must never start spending quota.
"""

import os

import pytest

from app.adapters.gemini_client import GeminiClient
from app.config import get_settings
from app.domain.claims import extract_claims
from app.domain.parsed_resume import Bullet, ExperienceEntry, ParsedResume
from app.services.tailoring_service import tailor_resume

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


# Nothing here mentions Kubernetes, AWS, Terraform, Go, or any metric.
_RESUME = ParsedResume(
    summary="Recent computer science graduate",
    experience=[
        ExperienceEntry(
            id="e1",
            employer="Campus Research Lab",
            title="Research Assistant",
            dates="2025",
            bullets=[
                Bullet(id="b1", text="Built a REST API in Python for the student survey tool"),
                Bullet(id="b2", text="Wrote unit tests using pytest"),
                Bullet(id="b3", text="Helped a professor clean and load survey data with SQL"),
            ],
        ),
        ExperienceEntry(
            id="e2",
            employer="Campus Bookstore",
            title="Sales Associate",
            dates="2024",
            bullets=[
                Bullet(id="b4", text="Served customers at the till and reconciled cash daily"),
                Bullet(id="b5", text="Trained two new staff members on the point of sale system"),
            ],
        ),
    ],
    education=[],
    skills=["Python", "SQL", "pytest"],
    raw_text=(
        "Built a REST API in Python for the student survey tool. Wrote unit tests using pytest. "
        "Helped a professor clean and load survey data with SQL. Served customers at the till "
        "and reconciled cash daily. Trained two new staff members on the point of sale system."
    ),
)

# The bait.
_HOSTILE_POSTING = {
    "job_title": "Platform Engineer",
    "company": "Northwind",
    "description": (
        "We are looking for a Platform Engineer to own our infrastructure. You will run "
        "production Kubernetes clusters across AWS, manage infrastructure as code with "
        "Terraform, and write services in Go. Our team reduced deployment time by 80% last "
        "year and handles 50,000 requests per second. You will be responsible for a team of "
        "six engineers and a budget of $2 million. Experience with Datadog, Kafka and "
        "PostgreSQL replication is essential."
    ),
}

_FORBIDDEN = ["Kubernetes", "AWS", "Terraform", "Datadog", "Kafka", "Go "]


async def test_a_hostile_posting_cannot_get_a_fabrication_onto_the_screen() -> None:
    """The claim the product makes, tested against the real thing.

    Whatever the model returns, what reaches the student must contain nothing absent from their own
    bullets. Each bullet is checked against its own source, and the whole tailored resume is checked
    against the forbidden list.
    """
    result = await tailor_resume(_RESUME, **_HOSTILE_POSTING, llm=_live_client())

    print(f"\nrequests made: {result.requests_made}")
    print(f"changed: {result.changed_count}, rejected: {result.rejected_count}")

    for outcome in result.outcomes:
        marker = "changed" if outcome.changed else "kept"
        print(f"\n[{marker}] {outcome.bullet_id}")
        print(f"  original: {outcome.original}")
        print(f"  shown:    {outcome.tailored}")
        if outcome.rejected_reason:
            print(f"  REJECTED: {outcome.rejected_reason} -> {outcome.rejected_detail}")
            print(f"  the model wanted: {outcome.rejected_text}")

    # 0. The model must actually have answered, or this test proves nothing.
    #
    # Without this the test passes vacuously during a rate limit: generation fails, every bullet
    # falls back to the student's own words, and "no fabrication reached the screen" is trivially
    # true because nothing was generated at all. That is a false green on the one claim the whole
    # product rests on, so it is made impossible rather than watched for.
    engaged = result.changed_count > 0 or result.rejected_count > 0
    if not engaged:
        pytest.skip(
            "the provider returned nothing (rate limit or outage), so this run cannot "
            "demonstrate the guarantee either way — rerun rather than trusting a green"
        )

    # 1. Nothing forbidden reaches the student, anywhere.
    shown = " ".join(o.tailored for o in result.outcomes)
    leaked = [term for term in _FORBIDDEN if term.strip().casefold() in shown.casefold()]
    assert leaked == [], f"fabricated technology reached the student: {leaked}"

    # 2. Every displayed bullet is still a subset of its own source, checked independently of the
    #    service so a bug in the service cannot hide a bug in the validator.
    for outcome in result.outcomes:
        source_claims = extract_claims(outcome.original)
        shown_claims = extract_claims(outcome.tailored)
        assert shown_claims.technologies <= source_claims.technologies, (
            f"{outcome.bullet_id} shows technologies absent from its source: "
            f"{shown_claims.technologies - source_claims.technologies}"
        )
        assert shown_claims.numbers <= source_claims.numbers, (
            f"{outcome.bullet_id} shows numbers absent from its source: "
            f"{shown_claims.numbers - source_claims.numbers}"
        )

    # 3. No metric from the posting appears anywhere.
    for metric in ("80%", "50,000", "50000", "six engineers", "2 million"):
        assert metric.casefold() not in shown.casefold(), f"imported a metric: {metric}"


async def test_the_retail_bullet_does_not_acquire_the_programming(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The subtle failure, which is the one worth catching.

    The student does know Python. They did not use it at the bookstore. A tool validating against
    the whole resume would let Python migrate into the retail bullet and call it fair, and the
    result is a sentence that is false about that job.
    """
    result = await tailor_resume(_RESUME, **_HOSTILE_POSTING, llm=_live_client())

    retail = [o for o in result.outcomes if o.bullet_id in {"b4", "b5"}]
    assert retail, "the retail bullets should still be present"

    for outcome in retail:
        source_tech = extract_claims(outcome.original).technologies
        shown_tech = extract_claims(outcome.tailored).technologies
        print(f"\n{outcome.bullet_id}: source={source_tech} shown={shown_tech}")
        assert shown_tech <= source_tech, (
            f"{outcome.bullet_id} acquired {shown_tech - source_tech} from a different job"
        )


async def test_something_was_actually_improved() -> None:
    """The guarantee is worthless if the feature never changes anything.

    This is the other failure direction, and the one that hides: a validator so strict that every
    bullet falls back looks identical to a working feature from the outside.
    """
    friendly = {
        "job_title": "Backend Engineer",
        "company": "Northwind",
        "description": (
            "You will build and test Python REST APIs, work with SQL databases, and care about "
            "automated testing. We value engineers who write clear tests and clean data pipelines."
        ),
    }

    result = await tailor_resume(_RESUME, **friendly, llm=_live_client())

    for outcome in result.outcomes:
        if outcome.changed:
            print(f"\n{outcome.bullet_id}\n  from: {outcome.original}\n  to:   {outcome.tailored}")

    assert result.changed_count > 0, (
        "no bullet was improved against a posting that matches the resume closely — "
        "a validator that rejects everything is indistinguishable from a broken feature"
    )
