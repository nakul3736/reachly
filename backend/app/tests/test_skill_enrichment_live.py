"""Live verification of skill enrichment. Gated, and deliberately cheap.

Two environment variables rather than one: `GEMINI_LIVE_TESTS=1` and a key. A configured key
alone must never start spending quota, because the key is present in ordinary development.

This exists because the offline tests prove the plumbing and say nothing about whether a real
model, reading a real description, returns skills that are actually in it. That is the only
claim ADR 0011 rests on, and it is not provable with a fake.
"""

import os

import pytest

from app.adapters.gemini_client import GeminiClient
from app.config import get_settings
from app.domain.skill_extraction import extract_skills
from app.services.skill_enrichment_service import _ask, _is_evidenced

pytestmark = pytest.mark.skipif(
    os.getenv("GEMINI_LIVE_TESTS") != "1" or not os.getenv("GEMINI_API_KEY"),
    reason="set GEMINI_LIVE_TESTS=1 and GEMINI_API_KEY to run",
)


def _live_client() -> GeminiClient:
    settings = get_settings()
    return GeminiClient(
        api_key=os.environ["GEMINI_API_KEY"],
        model=settings.gemini_model,
        timeout_seconds=60.0,
    )


class FakeJob:
    """Just enough of a Job for the prompt builder, so this needs no database."""

    def __init__(self, source_job_id: str, title: str, description: str) -> None:
        self.source_job_id = source_job_id
        self.title = title
        self.description = description

    @property
    def evidence(self) -> str:
        return f"{self.title}\n{self.description}"


_CARE = FakeJob(
    "care-1",
    "Patient Care Assistant",
    "You will support residents with daily living, record vital signs accurately in our "
    "electronic charting system, escalate changes in condition to the charge nurse, and "
    "maintain a calm environment for families during difficult conversations. Comfort "
    "with lifting and transferring residents safely is essential.",
)

_LOGISTICS = FakeJob(
    "log-2",
    "Warehouse Coordinator",
    "Coordinate inbound and outbound shipments, reconcile stock counts against our "
    "records, own the receiving process end to end, and negotiate collection windows "
    "with carriers. You will be comfortable reading a manifest and spotting "
    "discrepancies before they reach the customer.",
)

_PLATFORM = FakeJob(
    "plat-3",
    "Platform Engineer",
    "You will own the reliability of a service used by every team in the company, take "
    "part in an on-call rotation, and drive down the time it takes a change to reach "
    "production.",
)

# Written in the register the vocabulary reads worst: duties in prose, few product names. If
# enrichment cannot add anything here it cannot add anything at all.
_POSTINGS = [_CARE, _LOGISTICS, _PLATFORM]


async def test_the_model_returns_skills_that_are_actually_in_the_description() -> None:
    """One request, three postings, every answer checked against its own source text."""
    client = _live_client()

    answers = await _ask(client, _POSTINGS)

    assert set(answers) == {"care-1", "log-2", "plat-3"}, (
        f"every posting must be answered under the id it was given, got {sorted(answers)}"
    )

    for job in _POSTINGS:
        returned = answers[job.source_job_id]
        assert returned, f"{job.source_job_id} came back with no skills at all"

        kept = [s for s in returned if _is_evidenced(s, job.evidence)]
        # The interesting number. A model that mostly invents would show a low ratio here, and
        # the evidence guard would be carrying the feature rather than confirming it.
        ratio = len(kept) / len(returned)
        print(f"\n{job.source_job_id}: {len(kept)}/{len(returned)} evidenced -> {sorted(kept)}")
        print(f"  discarded: {sorted(set(returned) - set(kept))}")
        assert ratio >= 0.5, f"{job.source_job_id} mostly unevidenced: {returned}"


async def test_enrichment_finds_what_the_vocabulary_cannot() -> None:
    """ADR 0011's justification, stated as a test.

    43% of graduate-reachable postings in the real index yield nothing from the vocabulary,
    because they are care, logistics and retail roles described in prose. If a model adds
    nothing beyond the vocabulary on such a posting then the ADR is wrong and this fails.
    """
    client = _live_client()

    floor = extract_skills(_CARE.description)
    answers = await _ask(client, [_CARE])
    added = {s for s in answers["care-1"] if _is_evidenced(s, _CARE.evidence)} - floor

    print(f"\nvocabulary found {sorted(floor)}")
    print(f"model added {sorted(added)}")
    assert added, "enrichment added nothing to a posting the vocabulary cannot read"
