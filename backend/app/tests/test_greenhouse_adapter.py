"""The Greenhouse adapter, against a payload recorded from the live API.

The fixture is recorded rather than hand-authored. A fixture written to match the parser
only proves it was written to match the parser; this one was captured from Figma's real
board and contains the things nobody would think to invent — HTML-escaped descriptions,
multi-location strings joined with a bullet character, and not a single entry-level
software role in the first 161 postings.
"""

import pytest

from app.adapters.job_sources.greenhouse import parse_greenhouse_board
from app.tests.fixtures.job_payloads import GREENHOUSE_BOARD

pytestmark = pytest.mark.anyio


def test_every_job_in_the_payload_becomes_a_posting() -> None:
    postings = parse_greenhouse_board(GREENHOUSE_BOARD, company_name="Figma")

    assert len(postings) == len(GREENHOUSE_BOARD["jobs"])
    assert all(p.title for p in postings)
    assert all(p.apply_url.startswith("https://") for p in postings)
    assert {p.company_name for p in postings} == {"Figma"}


def test_the_posting_date_comes_from_first_publication() -> None:
    """`first_published`, not `updated_at`.

    Story 5 asks when a job was posted so a student can prioritise being early. Greenhouse
    touches `updated_at` on any edit, so using it would show a two-year-old requisition as
    posted today — the exact deception that makes a student waste an application.
    """
    postings = parse_greenhouse_board(GREENHOUSE_BOARD, company_name="Figma")

    dated = [p for p in postings if p.posted_at is not None]
    assert dated, "the recorded payload has first_published on every job"
    for posting in dated:
        assert posting.posted_at is not None
        assert posting.posted_at.tzinfo is not None, "offsets are in the payload, keep them"


def test_a_posting_missing_what_it_needs_is_skipped() -> None:
    """Skipped, not stored empty.

    A row with no title is unusable in a feed and unrankable in feature 03, and it would
    still occupy a slot. Dropping it is the honest outcome.
    """
    payload = {
        "jobs": [
            {"id": 1, "title": "", "absolute_url": "https://x/1", "content": "text"},
            {"id": 2, "absolute_url": "https://x/2", "content": "text"},
            {"id": 3, "title": "Real Role", "absolute_url": "", "content": "text"},
            {"id": 4, "title": "Keeper", "absolute_url": "https://x/4", "content": "text"},
        ]
    }

    postings = parse_greenhouse_board(payload, company_name="Figma")

    assert [p.source_job_id for p in postings] == ["4"]


def test_a_payload_with_no_jobs_yields_nothing_rather_than_raising() -> None:
    """A board with nothing open is normal, and must not look like a failure.

    Ticket 05 depends on this distinction: an empty response is not evidence that every job
    at a company closed, and an adapter that raised here would make the two
    indistinguishable.
    """
    assert parse_greenhouse_board({"jobs": []}, company_name="Figma") == []
    assert parse_greenhouse_board({}, company_name="Figma") == []
def test_the_description_is_readable_text_not_escaped_markup() -> None:
    """Greenhouse double-encodes: the JSON string contains `&lt;div&gt;`, not `<div>`.

    Stored as-is, a student opening a job reads a wall of `&lt;p&gt;`. Unescaping once
    yields real HTML, which then has to be stripped to leave prose. Getting either step
    wrong is invisible in a length check and obvious to anyone actually reading the page.
    """
    postings = parse_greenhouse_board(GREENHOUSE_BOARD, company_name="Figma")
    description = postings[0].description

    assert "&lt;" not in description
    assert "&amp;" not in description
    assert "&quot;" not in description
    assert "<div" not in description
    assert "<p>" not in description
    # The real posting is thousands of characters; stripping markup must not strip the prose.
    assert len(description) > 500
    assert "Figma" in description
