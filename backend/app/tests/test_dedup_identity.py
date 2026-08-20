"""Identity for a posting: normalisation, fingerprints, and what must never collapse.

Two failure directions, and they are not symmetric. A duplicate shown twice is an annoyance the
student can see and ignore. A real job wrongly collapsed is an opportunity that never reaches
the
screen, and nothing in the interface can hint at what is missing. Every test that guards against
over-collapsing is therefore worth more than every test that guards against under-collapsing,
and
the thresholds are set accordingly.
"""

from app.domain.dedup import (
    fingerprint,
    level_marker,
    location_similarity,
    normalise_company,
    normalise_location,
    normalise_title,
    seniority_markers,
    title_similarity,
)

# --- company --------------------------------------------------------------------------


def test_legal_suffixes_do_not_change_a_company() -> None:
    """`Stripe, Inc.` on a board and `Stripe` on an aggregator are one employer."""
    assert normalise_company("Stripe, Inc.") == normalise_company("Stripe")
    assert normalise_company("Shopify Inc") == normalise_company("Shopify")
    assert normalise_company("Wealthsimple Ltd.") == normalise_company("Wealthsimple")
    assert normalise_company("Databricks LLC") == normalise_company("Databricks")
    assert normalise_company("SAP SE") == normalise_company("SAP")
    assert normalise_company("Bench Accounting Corp.") == normalise_company(
        "Bench Accounting"
    )


def test_case_and_whitespace_do_not_change_a_company() -> None:
    assert normalise_company("  FIGMA   ") == normalise_company("Figma")
    assert normalise_company("Match\tGroup") == normalise_company("Match Group")


def test_two_different_companies_stay_different() -> None:
    """The guard on the suffix rules. Stripping too eagerly merges unrelated employers."""
    assert normalise_company("Stripe") != normalise_company("Stripe Health")
    assert normalise_company("Shopify") != normalise_company("Shopify Plus Partners")
    # `Inc` inside a name rather than as a suffix.
    assert normalise_company("Include Health") != normalise_company("Health")


# --- title ----------------------------------------------------------------------------


def test_requisition_numbers_do_not_change_a_title() -> None:
    """The same posting carries different requisition ids on different surfaces."""
    base = normalise_title("Software Engineer")
    assert normalise_title("Software Engineer (REQ-4821)") == base
    assert normalise_title("Software Engineer #4821") == base
    assert normalise_title("Software Engineer - R12345") == base
    assert normalise_title("Software Engineer JR0093822") == base
    assert normalise_title("Software Engineer [12345]") == base


def test_remote_markers_do_not_change_a_title() -> None:
    base = normalise_title("Data Analyst")
    assert normalise_title("Data Analyst (Remote)") == base
    assert normalise_title("Data Analyst - Remote") == base
    assert normalise_title("Data Analyst, Remote") == base


def test_a_level_number_is_never_stripped_from_a_title() -> None:
    """The most dangerous over-normalisation available here.

    `Engineer II` and `Engineer III` are different jobs with different pay and different
    requirements. A requisition-stripping rule that also eats level markers would collapse a
    graduate-appropriate opening into a senior one and remove it from the feed.
    """
    assert normalise_title("Engineer II") != normalise_title("Engineer III")
    assert normalise_title("Engineer II") != normalise_title("Engineer")
    assert normalise_title("Analyst 3") != normalise_title("Analyst")
    assert normalise_title("Developer L3") != normalise_title("Developer L4")
    assert "ii" in normalise_title("Engineer II")


def test_case_and_punctuation_do_not_change_a_title() -> None:
    assert normalise_title("SOFTWARE ENGINEER") == normalise_title("Software Engineer")
    assert normalise_title("Software  Engineer") == normalise_title("Software Engineer")


# --- level markers, extracted so similarity cannot ignore them ------------------------


def test_level_markers_are_recognised() -> None:
    assert level_marker("Software Engineer II") == "2"
    assert level_marker("Software Engineer III") == "3"
    assert level_marker("Engineer L4") == "4"
    assert level_marker("Analyst 3") == "3"
    assert level_marker("Software Engineer") is None
    assert level_marker("Software Engineer, New Grad") is None


def test_a_year_is_not_a_level() -> None:
    """`Intern 2027` is a cohort, not a level, and four digits are never a job level."""
    assert level_marker("Software Engineer Intern 2027") is None
    assert level_marker("Summer 2026 Intern") is None


# --- location -------------------------------------------------------------------------


def test_country_names_do_not_change_a_location() -> None:
    """A board writes the country, an aggregator often does not."""
    assert normalise_location("Toronto, ON, Canada") == normalise_location("Toronto, ON")
    assert normalise_location("Austin, TX, United States") == normalise_location(
        "Austin, TX"
    )


def test_multi_location_order_does_not_change_a_location() -> None:
    """Lever joins its locations in one order and The Muse in another.

    Sorting the parts means the same set of cities produces the same identity regardless of
    which order a provider happened to list them in.
    """
    assert normalise_location("New York, San Francisco") == normalise_location(
        "San Francisco, New York"
    )


def test_remote_markers_do_not_change_a_location() -> None:
    assert normalise_location("Remote - Toronto") == normalise_location("Toronto")
    assert normalise_location(None) == normalise_location("")


def test_two_different_cities_stay_different() -> None:
    assert normalise_location("Toronto, ON") != normalise_location("Vancouver, BC")


def test_a_country_only_location_is_not_erased() -> None:
    """A bug found on real data, not by reasoning.

    Dropping country words unconditionally turned `Canada` and `United States` into the same
    empty
    string, so Stripe's `Credit Risk Strategy and Analytics` in each country produced one
    identical
    fingerprint and the two postings collapsed into one row. For a product about US and Canadian
    graduates, that hid half of them.
    """
    assert normalise_location("Canada") != normalise_location("United States")
    assert normalise_location("Canada") != ""
    assert normalise_location("Remote - US: All locations") != normalise_location(
        "Remote - Canada: Select locations"
    )


def test_a_country_is_still_dropped_when_a_city_is_present() -> None:
    """The behaviour the country stripping was for in the first place, which must survive."""
    assert normalise_location("Toronto, ON, Canada") == normalise_location("Toronto, ON")


def test_locations_that_disagree_score_low() -> None:
    assert location_similarity("Toronto, ON", "Vancouver, BC") < 0.50
    assert location_similarity("San Francisco", "New York") < 0.50


def test_locations_that_agree_score_high_despite_different_detail() -> None:
    assert location_similarity("Toronto", "Toronto, Ontario, Canada") >= 0.50
    assert location_similarity("New York, NY", "New York") >= 0.50
    assert location_similarity("Toronto, ON, Canada", "Toronto, ON") == 1.0


def test_a_missing_location_is_not_evidence_of_a_difference() -> None:
    """An aggregator copy frequently omits the location, and must still be able to match."""
    assert location_similarity(None, "Toronto, ON") == 1.0
    assert location_similarity("Toronto, ON", "") == 1.0


def test_a_stated_seniority_prevents_a_collapse() -> None:
    """The second bug real data exposed.

    `Infrastructure Software Engineer` and `Senior Infrastructure Software Engineer` differ by
    one
    word out of five and score 0.90 on sorted tokens, so they collapsed — putting a senior role
    in
    a graduate's feed and removing the opening they could actually apply for. Level markers
    caught
    `II` against `III`; nothing caught the word.
    """
    assert (
        title_similarity(
            "Infrastructure Software Engineer", "Senior Infrastructure Software Engineer"
        )
        < 0.90
    )
    assert title_similarity("Data Analyst", "Staff Data Analyst") < 0.90
    assert title_similarity("Product Manager", "Principal Product Manager") < 0.90


def test_seniority_words_that_disagree_are_decisive() -> None:
    assert title_similarity("Junior Developer", "Senior Developer") == 0.0
    assert title_similarity("Graduate Analyst", "Lead Analyst") == 0.0


def test_seniority_markers_are_recognised() -> None:
    assert seniority_markers("Senior Engineer") == {"senior"}
    assert seniority_markers("Junior Engineer") == {"junior"}
    assert seniority_markers("New Grad Engineer") == {"graduate"}
    assert seniority_markers("Software Engineer") == frozenset()


def test_abbreviations_resolve_to_the_same_rank() -> None:
    """A board writing `Sr.` and an aggregator writing `Senior` must still match."""
    assert seniority_markers("Sr. Engineer") == seniority_markers("Senior Engineer")
    assert seniority_markers("Jr Analyst") == seniority_markers("Junior Analyst")
    assert seniority_markers("New Grad Engineer") == seniority_markers("Graduate Engineer")


def test_adjacent_ranks_are_distinct_ranks() -> None:
    """Found on a board outside the seed set, and the reason ranks are not bucketed.

    Discord lists `Senior Data Scientist, Causal Inference + Experimentation` and `Staff Data
    Scientist, Causal Inference & Experimentation`. Treating staff and senior as one rank left
    nothing to separate two otherwise-identical titles, and they collapsed. Two rungs of one
    ladder are two different jobs.
    """
    assert seniority_markers("Staff Engineer") != seniority_markers("Senior Engineer")
    assert seniority_markers("Principal Engineer") != seniority_markers("Staff Engineer")
    assert (
        title_similarity(
            "Staff Data Scientist, Causal Inference", "Senior Data Scientist, Causal Inference"
        )
        == 0.0
    )


def test_a_shared_state_does_not_make_two_towns_alike() -> None:
    """The third bug real data exposed.

    Masonicare's `Nursing Assistant` in Wallingford and in Stonington are two jobs in two towns.
    The `CT` they share pulled their similarity above the threshold and merged them, hiding one
    of
    two openings a student could have applied to.
    """
    assert location_similarity("Wallingford, CT", "Stonington, CT") < 0.50


def test_a_differing_state_is_decisive_even_with_the_same_city_name() -> None:
    """`Portland, OR` and `Portland, ME` share a whole city name and are 2,000 miles apart."""
    assert location_similarity("Portland, OR", "Portland, ME") == 0.0
    assert location_similarity("Vancouver, BC", "Vancouver, WA") == 0.0


# --- the fingerprint ------------------------------------------------------------------


def test_the_same_posting_from_two_sources_fingerprints_identically() -> None:
    """The whole point: a board copy and an aggregator copy of one job agree."""
    board = fingerprint(
        company="Shopify Inc.",
        title="Software Engineer (REQ-1029)",
        location="Toronto, ON, Canada",
    )
    aggregator = fingerprint(
        company="Shopify", title="Software Engineer", location="Toronto, ON"
    )
    assert board == aggregator


def test_the_fingerprint_is_content_derived_not_a_provider_id() -> None:
    """No two providers share an id, so identity cannot come from one.

    Same content, different provider ids, same fingerprint — which is only possible because the
    id is never an input.
    """
    one = fingerprint(company="Figma", title="Product Designer", location="Remote")
    two = fingerprint(company="Figma", title="Product Designer", location="Remote")
    assert one == two
    assert len(one) == 32


def test_different_jobs_fingerprint_differently() -> None:
    base = fingerprint(company="Figma", title="Engineer", location="Toronto, ON")
    assert base != fingerprint(company="Figma", title="Designer", location="Toronto, ON")
    assert base != fingerprint(company="Linear", title="Engineer", location="Toronto, ON")
    assert base != fingerprint(company="Figma", title="Engineer", location="Vancouver, BC")
    assert base != fingerprint(company="Figma", title="Engineer II", location="Toronto, ON")


# --- similarity -----------------------------------------------------------------------


def test_word_order_does_not_reduce_similarity() -> None:
    """Token-set, so a reordered title still reads as the same role."""
    score = title_similarity(
        "Software Engineer, New Grad", "New Grad Software Engineer"
    )
    assert score > 0.90


def test_unrelated_titles_score_low() -> None:
    assert title_similarity("Software Engineer", "Marketing Manager") < 0.75
    assert title_similarity("Data Analyst", "Security Officer") < 0.75


def test_a_subset_title_is_not_a_match() -> None:
    """The measurement that changed the algorithm.

    `token_set_ratio`, which the ticket specified, scores every pair below at 100 because it
    treats a subset as a perfect match. Each is two different openings, so token-set could not
    be
    used and `token_sort_ratio` replaced it.
    """
    assert title_similarity("Data Analyst", "Senior Data Analyst") < 0.90
    assert title_similarity("Software Engineer", "Software Engineer, Machine Learning") < 0.90
    assert title_similarity("Engineer", "Engineer, Infrastructure Platform") < 0.90


def test_reordering_still_scores_as_identical() -> None:
    """What token-set was chosen for in the first place, and which survives the change."""
    assert title_similarity("Support Specialist, Product", "Product Support Specialist") > 0.95
    assert title_similarity("Associate Product Manager", "Product Manager, Associate") > 0.95


def test_titles_differing_only_by_level_are_forced_apart() -> None:
    """Token similarity alone would collapse these, and that is the expensive mistake.

    `Engineer II` against `Engineer III` scores well above the fuzzy threshold on raw tokens —
    the strings differ by one character. Returning a low score here is deliberate: the level
    marker is the whole content of the difference, so it has to dominate rather than be averaged
    away.
    """
    assert title_similarity("Software Engineer II", "Software Engineer III") < 0.75
    assert title_similarity("Developer L3", "Developer L4") < 0.75
