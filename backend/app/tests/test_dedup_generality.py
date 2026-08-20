"""Whether the dedup rules generalise, or were fitted to the boards they were built against.

The same guard as `test_classification_generality.py`, for the same reason. Rules tuned until
the
seeded boards look right will look right on the seeded boards and nowhere else, and the failure
is
invisible from inside the sample.

**These tests assert properties, not answers.** A table of expected verdicts for specific titles
would be the same overfitting one level up: it would encode the outcomes the current thresholds
happen to produce and then defend them against improvement. What is asserted instead is what
must
hold for any employer's vocabulary — that nothing here is keyed to a company, that a rule stated
for one wording holds for its variants, and that the dangerous direction stays closed.

The vocabulary below deliberately comes from industries Reachly's seed boards do not cover:
healthcare, logistics, retail, hospitality, education, construction. Two of the three bugs this
module has had were found on data outside the sample, so unseen vocabulary is where the tests
look.
"""

import itertools

from app.domain.dedup import (
    fingerprint,
    level_marker,
    location_similarity,
    normalise_company,
    normalise_title,
    seniority_markers,
    title_similarity,
)

# Titles from industries outside the seeded technology boards. If the rules only work on
# software
# job titles, they fail the product: The Muse's entry-level feed is mostly not software, and it
# is
# where most of the entry-level postings are.
UNSEEN_TITLES = [
    "Registered Nurse, Medical Surgical",
    "Certified Nursing Assistant",
    "Warehouse Associate",
    "Class A Delivery Driver",
    "Retail Sales Associate",
    "Restaurant General Manager",
    "Line Cook",
    "Substitute Teacher, Elementary",
    "Journeyman Electrician",
    "Heavy Equipment Operator",
    "Insurance Claims Adjuster",
    "Dental Hygienist",
    "Physical Therapy Aide",
    "Bank Teller",
    "Loan Processor",
    "Veterinary Technician",
    "Groundskeeper",
    "Security Officer, Overnight",
    "Housekeeping Attendant",
    "Pharmacy Technician Trainee",
]

UNSEEN_COMPANIES = [
    "Mercy General Hospital",
    "Northland Freight Ltd.",
    "Harborview Grocers Inc.",
    "Sandpiper Hospitality Group LLC",
    "Cedar Ridge School District",
    "Ironwood Construction Corp.",
    "Bluewater Insurance Company",
    "Kettle Creek Veterinary",
]

UNSEEN_LOCATIONS = [
    "Saskatoon, SK, Canada",
    "Kitchener, ON",
    "Boise, ID",
    "Chattanooga, TN",
    "Moncton, NB, Canada",
    "Fargo, ND",
    "Remote - US: All locations",
    "Hybrid - Sudbury, ON",
]


# --- nothing is keyed to a company ----------------------------------------------------


def test_no_rule_names_a_company() -> None:
    """The most direct overfitting check available: read the module and look for the seed list.

    A rule that mentions Stripe, Shopify or Figma by name would work on the boards it was
    written
    against and silently do nothing everywhere else.
    """
    from pathlib import Path

    import app.domain.dedup as module
    from app.seed_boards import SEED_BOARDS

    source = Path(module.__file__).read_text(encoding="utf-8")

    # Company names appear in this file only inside comments that record where a bug was found.
    # Splitting the code from the prose is what makes the assertion meaningful.
    without_comments = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    # Every other segment of a docstring-delimited split is executable code.
    segments = without_comments.split('"""')
    executable = "".join(segments[::2])

    for board in SEED_BOARDS:
        assert board.company_name.casefold() not in executable.casefold(), (
            f"{board.company_name} is named in the rules, which means they are fitted to it"
        )
        assert board.token.casefold() not in executable.casefold()


# --- the rules hold for unseen vocabulary ---------------------------------------------


def test_every_unseen_title_normalises_to_something() -> None:
    """A normaliser that empties an unfamiliar title would make everything match everything."""
    for title in UNSEEN_TITLES:
        assert normalise_title(title).strip(), title


def test_no_two_unseen_titles_collide(count_threshold: float = 0.90) -> None:
    """Twenty unrelated jobs must produce twenty identities.

    This is the property that matters most, because the failure it guards is silent: a collision
    here means two real openings become one feed row and the student never learns the other
    existed.
    """
    for left, right in itertools.combinations(UNSEEN_TITLES, 2):
        assert title_similarity(left, right) < count_threshold, f"{left} vs {right}"


def test_no_two_unseen_companies_collide() -> None:
    normalised = [normalise_company(name) for name in UNSEEN_COMPANIES]
    assert len(set(normalised)) == len(UNSEEN_COMPANIES)


def test_legal_suffix_stripping_works_on_unseen_names() -> None:
    """Stated as a rule about suffixes, so it must hold for names never seen before."""
    assert normalise_company("Northland Freight Ltd.") == normalise_company(
        "Northland Freight"
    )
    assert normalise_company("Harborview Grocers Inc.") == normalise_company(
        "Harborview Grocers"
    )
    assert normalise_company("Ironwood Construction Corp.") == normalise_company(
        "Ironwood Construction"
    )


def test_no_two_unseen_locations_are_treated_as_one_place() -> None:
    """Includes the cities the country classifier is known to miss.

    `location.py` recognises Saskatoon and Kitchener only through province codes, not a city
    list.
    Dedup must still keep them apart, because a student in Saskatoon needs the Saskatoon
    posting.
    """
    for left, right in itertools.combinations(UNSEEN_LOCATIONS, 2):
        assert location_similarity(left, right) < 0.90, f"{left} vs {right}"


# --- the dangerous direction stays closed on unseen data ------------------------------


def test_a_seniority_word_prevents_collapse_for_any_unseen_title() -> None:
    """Stated as a rule about ranks, so it holds for jobs in any industry."""
    for title in UNSEEN_TITLES:
        for rank in ("Senior", "Junior", "Lead", "Principal"):
            assert title_similarity(title, f"{rank} {title}") < 0.90, f"{rank} {title}"


def test_a_level_number_prevents_collapse_for_any_unseen_title() -> None:
    for title in UNSEEN_TITLES:
        assert title_similarity(f"{title} II", f"{title} III") < 0.75


def test_a_differing_region_prevents_collapse_for_any_unseen_city() -> None:
    """A two-letter code rule rather than a table of states, so unlisted regions work too."""
    assert location_similarity("Moncton, NB", "Moncton, ON") == 0.0
    assert location_similarity("Springfield, IL", "Springfield, MO") == 0.0
    assert location_similarity("London, ON", "London, UK") == 0.0


def test_two_towns_sharing_a_region_are_still_two_towns() -> None:
    """The bug found on Masonicare's postings, restated for places outside that data."""
    assert location_similarity("Kitchener, ON", "Sudbury, ON") < 0.50
    assert location_similarity("Fargo, ND", "Bismarck, ND") < 0.50


# --- the rules that must keep firing --------------------------------------------------


def test_requisition_stripping_works_on_unseen_titles() -> None:
    for title in UNSEEN_TITLES:
        assert normalise_title(f"{title} (REQ-88213)") == normalise_title(title)
        assert normalise_title(f"{title} #4472") == normalise_title(title)


def test_an_aggregator_copy_of_an_unseen_posting_still_matches_its_board() -> None:
    """End to end on vocabulary from outside the sample, in the shape the sources produce it.

    The board writes the legal name, the requisition id and the full location; the aggregator
    writes the plain name and a shorter location. They have to agree.
    """
    for title, company, location in zip(
        UNSEEN_TITLES[:6], UNSEEN_COMPANIES[:6], UNSEEN_LOCATIONS[:6], strict=False
    ):
        city = location.split(",")[0]
        board = fingerprint(
            company=company, title=f"{title} (REQ-1234)", location=location
        )
        aggregator = fingerprint(
            company=normalise_company(company), title=title, location=city
        )
        # Not necessarily an exact fingerprint match, since the locations differ in detail — but
        # the pair must at least be judged similar enough to reach a collapse.
        assert title_similarity(f"{title} (REQ-1234)", title) >= 0.90
        assert location_similarity(location, city) >= 0.50
        assert isinstance(board, str) and isinstance(aggregator, str)


def test_level_markers_are_found_in_unseen_titles() -> None:
    for title in UNSEEN_TITLES:
        assert level_marker(f"{title} II") == "2"
        assert level_marker(title) is None


def test_seniority_markers_are_found_in_unseen_titles() -> None:
    """Adding a rank must always change the rank set, whatever the title already contains.

    Asserted as a change rather than as a specific value, because a title can legitimately hold
    two rank words: Retail Sales Associate uses "associate" as the job itself, and Senior
    Retail Sales Associate adds a rank on top. Demanding one canonical answer there would be
    asserting an implementation detail with no correct value.
    """
    for title in UNSEEN_TITLES:
        assert "senior" in seniority_markers(f"Senior {title}")
        assert seniority_markers(f"Senior {title}") != seniority_markers(title)


# --- the holdout must stay a holdout ---------------------------------------------------


def test_the_unseen_vocabulary_is_not_drifting_toward_the_seeded_boards() -> None:
    """Guards the guard.

    If someone later adds technology titles to these lists to make a threshold change pass, the
    holdout stops being a holdout and this file stops proving anything. The check is crude on
    purpose: it fails loudly and is easy to understand when it does.
    """
    software_words = {
        "engineer",
        "developer",
        "software",
        "data scientist",
        "designer",
        "product manager",
        "devops",
        "frontend",
        "backend",
    }
    for title in UNSEEN_TITLES:
        lowered = title.casefold()
        assert not any(word in lowered for word in software_words), (
            f"{title!r} belongs to the seeded sample's vocabulary, not a holdout"
        )
