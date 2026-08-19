"""Classifying a posting by what its title and location say.

Every title below is real, taken from the 2,586 postings ingested from ten live company
boards. That matters more than it sounds: the two hardest cases here are ones nobody would
have invented.

`Sr.` appears 205 times against `Senior` 513, so a rule keying on the long spelling alone
mislabels two hundred senior roles as unknown. And `CA` is ambiguous in the exact data we
have — `CA-Toronto` is Canada, `San Francisco, CA` is California — so a naive two-letter match
puts Bay Area jobs in the wrong country.

Spike 001's measurement also reproduces here: 59 of 2,586 titles carry any entry-level marker.
"""

import pytest

from app.domain.location import extract_location
from app.domain.role_family import Seniority, classify_role_family, classify_seniority

# --- seniority ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # Explicitly open to graduates.
        ("Software Engineer Intern", Seniority.ENTRY),
        ("Software Engineering Intern, Summer 2026", Seniority.ENTRY),
        ("New Grad Software Engineer", Seniority.ENTRY),
        ("Graduate Software Engineer", Seniority.ENTRY),
        ("Junior Data Analyst", Seniority.ENTRY),
        ("Jr. Backend Developer", Seniority.ENTRY),
        ("Software Engineer I", Seniority.ENTRY),
        ("Engineering Co-op", Seniority.ENTRY),
        ("Entry Level Analyst", Seniority.ENTRY),
        # Explicitly not.
        ("Senior Software Engineer", Seniority.SENIOR),
        ("Sr. Product Manager", Seniority.SENIOR),
        ("Sr Staff Engineer", Seniority.SENIOR),
        ("Staff Software Engineer", Seniority.SENIOR),
        ("Principal Engineer", Seniority.SENIOR),
        ("Engineering Manager", Seniority.SENIOR),
        ("Director, Product Management", Seniority.SENIOR),
        ("Head of Infrastructure", Seniority.SENIOR),
        ("Vice President, People Business Partner", Seniority.SENIOR),
        ("VP Engineering", Seniority.SENIOR),
        ("Software Engineer II", Seniority.SENIOR),
        ("Software Engineer IV", Seniority.SENIOR),
        ("Lead Designer", Seniority.SENIOR),
        # No signal at all. The commonest case, and it must stay honest.
        ("Software Engineer", Seniority.UNKNOWN),
        ("Account Executive", Seniority.UNKNOWN),
        ("Backend Developer", Seniority.UNKNOWN),
    ],
)
def test_seniority_is_read_from_the_title(title: str, expected: Seniority) -> None:
    assert classify_seniority(title) is expected


@pytest.mark.parametrize(
    "title",
    [
        "Senior Software Engineer Intern",
        "Staff Engineer, New Grad Program",
        "Manager, Graduate Recruiting",
        "Director of Junior Talent",
    ],
)
def test_a_senior_marker_beats_an_entry_marker(title: str) -> None:
    """Negative markers win, always.

    `Senior Software Engineer` contains `Engineer`; the word that decides is `Senior`. Getting
    this backwards fills a graduate's feed with roles requiring a decade of experience, which
    is the single fastest way to make the product useless.
    """
    assert classify_seniority(title) is Seniority.SENIOR


def test_an_unmarked_title_is_unknown_not_entry() -> None:
    """Guessing entry would put senior roles in a graduate's feed.

    Guessing senior would hide the plain `Software Engineer` postings that are often exactly
    what a graduate should apply to. Neither guess is honest, so the answer is that we do not
    know — and the feed lets a student include unknown deliberately.
    """
    assert classify_seniority("Software Engineer") is Seniority.UNKNOWN
    assert classify_seniority("") is Seniority.UNKNOWN


def test_roman_numeral_one_is_entry_but_only_as_its_own_word() -> None:
    """`Engineer I` is entry level. `Engineer II` is not, and neither is `IT Engineer`.

    A substring match on "I" would classify almost everything as entry level.
    """
    assert classify_seniority("Software Engineer I") is Seniority.ENTRY
    assert classify_seniority("Software Engineer II") is Seniority.SENIOR
    assert classify_seniority("IT Support Specialist") is Seniority.UNKNOWN


# --- role family ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineer", "software_engineering"),
        ("Backend Developer", "software_engineering"),
        ("Full Stack Engineer", "software_engineering"),
        ("Mobile Engineer, iOS", "software_engineering"),
        ("Data Scientist", "data_ml"),
        ("Machine Learning Engineer", "data_ml"),
        ("Data Analyst", "data_ml"),
        ("Site Reliability Engineer", "infrastructure"),
        ("DevOps Engineer", "infrastructure"),
        ("Security Engineer", "infrastructure"),
        ("QA Engineer", "quality"),
        ("Product Manager", "product"),
        ("Product Designer", "design"),
        ("Account Executive, Enterprise", "sales"),
        ("Solutions Architect", "sales"),
        ("Strategic Account Manager", "sales"),
        ("Customer Success Manager", "support"),
        ("Technical Support Engineer", "support"),
        ("Senior Accountant", "business"),
        ("Recruiter, Technical", "business"),
        ("Administrative Coordinator", "business"),
        ("Vice President, People Business Partner", "business"),
        ("Content Marketing Manager", "marketing"),
    ],
)
def test_role_family_is_read_from_the_title(title: str, expected: str) -> None:
    assert classify_role_family(title) == expected


def test_a_title_matching_nothing_is_other_rather_than_forced() -> None:
    """A classifier that quietly buckets what it does not understand is worse than one that
    admits it, because the wrong bucket is invisible and `other` is not."""
    assert classify_role_family("Chief of Staff to the CEO") == "other"
    assert classify_role_family("") == "other"


def test_engineer_in_a_sales_title_does_not_make_it_engineering() -> None:
    """`Solutions Engineer` and `Sales Engineer` are commercial roles.

    Both contain `Engineer`, and both would waste a graduate developer's evening. This is the
    distinction spike 001 said the filter exists for.
    """
    assert classify_role_family("Solutions Engineer") == "sales"
    assert classify_role_family("Sales Engineer, Enterprise") == "sales"


# --- location -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "country", "remote"),
    [
        # The ambiguity that makes this function necessary. Both forms are in the real data.
        ("CA-Toronto, CA-Montreal, CA-Vancouver", "CA", False),
        ("San Francisco, CA", "US", False),
        ("US-San Francisco, US-Chicago, US-New York", "US", False),
        ("US-Remote, US-San Francisco", "US", True),
        ("US-West Coast (Remote)", "US", True),
        ("New York, NY; San Francisco, CA; Seattle, WA", "US", False),
        ("San Francisco, CA; Chicago, IL & New York, NY", "US", False),
        ("Toronto, Ontario, Canada", "CA", False),
        ("Halifax, NS", "CA", False),
        ("Remote - US", "US", True),
        ("Remote", None, True),
        ("Japan", None, False),
        ("Singapore", None, False),
        ("Germany ", None, False),
        ("Bengaluru, India", None, False),
        ("", None, False),
    ],
)
def test_country_and_remote_are_derived_from_the_location_text(
    raw: str, country: str | None, remote: bool
) -> None:
    result = extract_location(raw)

    assert result.country == country
    assert result.is_remote is remote


def test_a_multi_country_posting_prefers_a_country_the_student_can_work_in() -> None:
    """Several boards list one requisition across continents.

    One country column cannot hold that, and dropping the posting would lose a real
    opportunity, so US or Canada wins when present. The full text stays in `location_raw`, so
    nothing is hidden — story 21.
    """
    assert extract_location("Toronto, ON • London, UK").country == "CA"
    assert extract_location("Berlin, Germany • New York, NY").country == "US"


def test_the_bullet_separator_in_greenhouse_locations_is_handled() -> None:
    """Ninety of the real postings join locations with a bullet character."""
    result = extract_location("San Francisco, CA • New York, NY • United States")

    assert result.country == "US"
    assert result.is_remote is False
