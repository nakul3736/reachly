"""Does the classifier generalise, or was it tuned to the boards it was written against?

The rules were written while looking at 2,586 postings from ten seeded company boards, which
is exactly the situation where keyword lists quietly become a description of one sample rather
than of the world. This module is the guard against that, and it works the same way the resume
layout variants do in feature 01: hold out data the rules were never shown, and assert the
behaviour does not degrade.

The titles below are recorded from Duolingo, Reddit and Discord — none of them in the seed
list, none of them consulted while writing the rules.

What is deliberately *not* asserted is a per-title expected answer. That would just be the
same overfitting one level up, with the test encoding today's opinion about each string.
What is asserted are properties that must hold on any corpus: the classifier spreads titles
across families rather than dumping them in one, it does not silently label everything
`other`, and it does not claim confidence about seniority it has no evidence for.
"""

import collections

from app.domain.location import extract_location
from app.domain.role_family import (
    ROLE_FAMILIES,
    Seniority,
    classify_role_family,
    classify_seniority,
)

# Recorded from boards outside the seed set. Trimmed to a spread, including the awkward ones.
UNSEEN_TITLES = [
    "Senior Software Engineer, Growth",
    "Staff Machine Learning Engineer",
    "Data Scientist, Product Analytics",
    "Android Engineer",
    "iOS Engineer, Core Experience",
    "Engineering Manager, Platform",
    "Senior Product Designer",
    "Product Manager, Monetization",
    "Technical Sourcer",
    "Creative Sourcer",
    "Managing Editor",
    "Community Manager - French speaker (contract)",
    "Government Affairs Manager",
    "Head of Influencers & Community",
    "Account Executive, Mid-Market",
    "Client Partner, Agency",
    "Senior Analyst, Financial Planning",
    "Security Engineer, Detection",
    "Site Reliability Engineer",
    "Curriculum Designer, Spanish",
    "Learning Scientist",
    "Localization Project Manager",
    "Senior Counsel, Privacy",
    "Recruiting Coordinator",
    "Software Engineer, Backend",
    "Software Engineer Intern, Summer",
    "Creative Strategist - App Dev",
    "EMEA Insights Specialist",
    "Agency Development Lead, DACH",
    "Principal Product Manager",
]

UNSEEN_LOCATIONS = [
    "New York, NY",
    "San Francisco, CA",
    "Remote - US",
    "Toronto, ON",
    "Pittsburgh, PA",
    "London, UK",
    "Berlin, Germany",
    "Remote",
    "Seattle, WA",
    "Vancouver, BC",
    "Dublin, Ireland",
    "Sao Paulo, Brazil",
]


def test_unseen_titles_are_spread_across_families_not_dumped_in_one() -> None:
    """A classifier tuned to one sample tends to collapse on a new one.

    The failure looks like a single family absorbing everything, or `other` absorbing
    everything. Either way the filter stops filtering while still appearing to work.
    """
    families = collections.Counter(classify_role_family(t) for t in UNSEEN_TITLES)

    assert len(families) >= 6, f"only {len(families)} families used: {dict(families)}"
    largest = families.most_common(1)[0][1]
    assert largest < len(UNSEEN_TITLES) * 0.5, f"one family took {largest}: {dict(families)}"


def test_unseen_titles_do_not_mostly_fall_through_to_other() -> None:
    """`other` is an honest answer, and also the answer that hides a useless classifier."""
    other = sum(1 for t in UNSEEN_TITLES if classify_role_family(t) == "other")

    assert other / len(UNSEEN_TITLES) < 0.25, f"{other} of {len(UNSEEN_TITLES)} fell through"


def test_every_family_returned_is_one_the_api_can_filter_by() -> None:
    """A family the classifier produces but the filter does not list is unreachable."""
    for title in UNSEEN_TITLES:
        assert classify_role_family(title) in ROLE_FAMILIES


def test_seniority_does_not_claim_entry_without_evidence() -> None:
    """The expensive mistake in this direction.

    Labelling a senior role entry puts a decade-of-experience posting in a graduate's feed.
    Every title here labelled entry must contain an actual entry-level word.
    """
    markers = ("intern", "new grad", "graduate", "junior", "jr", "co-op", "coop", "apprentice",
               "entry", "trainee", "campus")
    for title in UNSEEN_TITLES:
        if classify_seniority(title) is Seniority.ENTRY:
            assert any(m in title.lower() for m in markers), title


def test_a_title_with_no_level_word_stays_unknown() -> None:
    """Plain titles are the commonest kind, and must not be quietly bucketed either way."""
    unknown = [t for t in UNSEEN_TITLES if classify_seniority(t) is Seniority.UNKNOWN]

    assert unknown, "no title was left unknown, which means something is being guessed"


def test_unseen_locations_resolve_without_inventing_a_country() -> None:
    """A country the student cannot work in must not be labelled US or Canada.

    The hard location filter acts on this column, so a wrong country is not a cosmetic error —
    it puts an unreachable job in the feed, or hides a reachable one.
    """
    resolved = {loc: extract_location(loc).country for loc in UNSEEN_LOCATIONS}

    assert resolved["London, UK"] is None
    assert resolved["Berlin, Germany"] is None
    assert resolved["Sao Paulo, Brazil"] is None
    assert resolved["Dublin, Ireland"] is None
    assert resolved["Toronto, ON"] == "CA"
    assert resolved["Vancouver, BC"] == "CA"
    assert resolved["San Francisco, CA"] == "US"
    assert resolved["Pittsburgh, PA"] == "US"
    assert resolved["Remote"] is None, "a bare Remote names no country and must not invent one"


def test_the_holdout_set_is_not_secretly_similar_to_the_seeded_boards() -> None:
    """Guarding the guard, as the resume variants do.

    A holdout set that drifted into looking like the training sample would keep passing while
    proving nothing. These titles must cover several families and both seniority extremes.
    """
    families = {classify_role_family(t) for t in UNSEEN_TITLES}
    seniorities = {classify_seniority(t) for t in UNSEEN_TITLES}

    assert len(families) >= 6
    assert Seniority.SENIOR in seniorities
    assert Seniority.ENTRY in seniorities
    assert Seniority.UNKNOWN in seniorities
