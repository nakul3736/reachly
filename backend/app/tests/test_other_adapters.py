"""Lever, Ashby and The Muse.

Three providers that agree with Greenhouse on almost nothing, each recorded from its live API.
The disagreements are the point, and each one below is a real trap:

* Lever returns a bare JSON array rather than an object, puts the title in `text`, and dates
  `createdAt` in **epoch milliseconds** where Greenhouse uses ISO 8601.
* Ashby supplies `descriptionPlain` already stripped, and states `isRemote` explicitly rather
  than leaving it to be read out of a location string.
* The Muse nests the company, wraps locations in objects, calls the title `name`, and reports
  4,493 pages — so pagination has to be bounded rather than followed to the end.
"""

import pytest

from app.adapters.job_sources.ashby import parse_ashby_board
from app.adapters.job_sources.lever import parse_lever_board
from app.adapters.job_sources.muse import parse_muse_page
from app.tests.fixtures.job_payloads import ASHBY_BOARD, LEVER_BOARD, MUSE_PAGE

pytestmark = pytest.mark.anyio


# --- Lever ----------------------------------------------------------------------------


def test_lever_parses_its_array_payload() -> None:
    postings = parse_lever_board(LEVER_BOARD, company_name="Match Group")

    assert len(postings) == len(LEVER_BOARD)
    assert all(p.source == "lever" for p in postings)
    assert all(p.title for p in postings)
    assert all(p.apply_url.startswith("https://") for p in postings)


def test_lever_reads_its_epoch_millisecond_dates() -> None:
    """`createdAt` is 1779223091267, not an ISO string.

    Passed to a seconds-based parser this becomes a date in the year 58,000; treated as ISO it
    fails and the posting looks undated. Either way story 5 breaks, and a student cannot tell
    which openings are fresh.
    """
    postings = parse_lever_board(LEVER_BOARD, company_name="Match Group")

    dated = [p for p in postings if p.posted_at]
    assert dated
    for posting in dated:
        assert posting.posted_at is not None
        assert posting.posted_at.tzinfo is not None
        assert 2000 < posting.posted_at.year < 2100, posting.posted_at


def test_lever_takes_its_location_from_the_categories_object() -> None:
    postings = parse_lever_board(LEVER_BOARD, company_name="Match Group")

    assert any(p.location_raw for p in postings)


def test_lever_descriptions_are_plain_text() -> None:
    postings = parse_lever_board(LEVER_BOARD, company_name="Match Group")

    for posting in postings:
        assert "<div" not in posting.description
        assert "&lt;" not in posting.description


def test_lever_keeps_the_requirements_not_just_the_opening_paragraph() -> None:
    """Lever splits a posting across `description` and `additional`.

    Storing only the first leaves out the responsibilities and requirements — the part a
    student actually needs in order to decide, and the part feature 04 tailors against.
    """
    postings = parse_lever_board(LEVER_BOARD, company_name="Match Group")

    assert max(len(p.description) for p in postings) > 2000


# --- Ashby ----------------------------------------------------------------------------


def test_ashby_parses_its_board() -> None:
    postings = parse_ashby_board(ASHBY_BOARD, company_name="Linear")

    assert postings
    assert all(p.source == "ashby" for p in postings)
    assert all(p.title and p.apply_url for p in postings)


def test_ashby_remote_flag_is_taken_from_the_provider_not_guessed() -> None:
    """Ashby states it, so reading the location string would be inventing a worse answer.

    A posting marked remote with a location of `Europe` would otherwise read as not remote.
    """
    postings = parse_ashby_board(ASHBY_BOARD, company_name="Linear")

    assert any(p.is_remote_hint is not None for p in postings)


def test_ashby_unlisted_jobs_are_skipped() -> None:
    """`isListed: false` means the employer has taken it down but the API still returns it."""
    payload = {
        "jobs": [
            {
                "id": "a",
                "title": "Listed Role",
                "jobUrl": "https://x/a",
                "descriptionPlain": "text",
                "isListed": True,
            },
            {
                "id": "b",
                "title": "Hidden Role",
                "jobUrl": "https://x/b",
                "descriptionPlain": "text",
                "isListed": False,
            },
        ]
    }

    postings = parse_ashby_board(payload, company_name="Linear")

    assert [p.title for p in postings] == ["Listed Role"]


# --- The Muse -------------------------------------------------------------------------


def test_muse_parses_a_page() -> None:
    postings = parse_muse_page(MUSE_PAGE)

    assert postings
    assert all(p.source == "muse" for p in postings)
    assert all(p.title for p in postings)


def test_muse_postings_are_unverified() -> None:
    """The Muse is an aggregator, so its postings are a copy of unknown age.

    Presenting them as company-confirmed is the deception the whole feed is built to avoid, and
    it also decides which record survives dedup.
    """
    postings = parse_muse_page(MUSE_PAGE)

    assert all(p.is_verified is False for p in postings)


def test_muse_company_comes_from_the_nested_object() -> None:
    """The company is not a top-level string here, and the title is `name`, not `title`."""
    postings = parse_muse_page(MUSE_PAGE)

    assert all(p.company_name for p in postings)
    assert not any(p.company_name.startswith("{") for p in postings)


def test_muse_carries_its_own_level_claim() -> None:
    """Muse states the level, and its own claim beats our inference from the title.

    `Security Officer` contains no seniority word at all, so title inference returns unknown
    while Muse is explicitly saying entry level. Ignoring that would discard the one thing this
    source is good for.
    """
    postings = parse_muse_page(MUSE_PAGE)

    assert any(p.seniority_hint == "entry" for p in postings)


def test_muse_descriptions_are_plain_text() -> None:
    postings = parse_muse_page(MUSE_PAGE)

    for posting in postings:
        assert "<p>" not in posting.description
        assert "<div" not in posting.description
    assert max(len(p.description) for p in postings) > 200


def test_muse_locations_are_unwrapped_from_their_objects() -> None:
    postings = parse_muse_page(MUSE_PAGE)

    located = [p for p in postings if p.location_raw]
    assert located
    for posting in located:
        assert posting.location_raw is not None
        assert "{" not in posting.location_raw


# --- the four payloads must not have drifted into looking alike -----------------------


def test_the_recorded_payloads_are_structurally_different() -> None:
    """Guarding the guard, as the resume variants do.

    Four fixtures that happened to share a shape would pass every test above while proving
    nothing about the adapters' independence.
    """
    from app.tests.fixtures.job_payloads import GREENHOUSE_BOARD

    assert isinstance(LEVER_BOARD, list), "Lever is a bare array"
    assert isinstance(GREENHOUSE_BOARD, dict) and "jobs" in GREENHOUSE_BOARD
    assert isinstance(ASHBY_BOARD, dict) and "jobs" in ASHBY_BOARD
    assert isinstance(MUSE_PAGE, dict) and "results" in MUSE_PAGE

    # The title lives under a different key in three of the four.
    assert "title" in GREENHOUSE_BOARD["jobs"][0]
    assert "text" in LEVER_BOARD[0]
    assert "name" in MUSE_PAGE["results"][0]
