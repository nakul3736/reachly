"""The tailoring validator — the feature that makes this product different.

ADR 0006: a tailored bullet may rephrase, reorder and re-emphasise, and may never introduce a
technology, employer, metric or claim absent from the source bullet. Enforced here, deterministically,
after generation and before anything reaches the student.

The two ways this can fail are opposite and both fatal:

- **Too permissive** lets an invented technology through, and the student takes a fabrication into
  an interview. That is the career risk the whole product exists to remove.
- **Too strict** rejects every rewrite, so the feature falls back to the original bullet every time
  and does nothing while appearing to work. This project has already shipped that failure twice —
  once when skill extraction returned 7 skills for a resume listing 46, once when a build guard
  deleted the entire frontend — and both times everything looked fine.
"""

import pytest

from app.domain.claims import extract_claims, normalise_number
from app.domain.tailoring import RejectionReason, validate_rewrite


class TestRephrasingIsAllowed:
    """The permitted transformation. If these fail the feature is useless."""

    @pytest.mark.parametrize(
        ("source", "rewrite"),
        [
            (
                "Built a REST API in Python for the student portal",
                "Developed a Python REST API serving the student portal",
            ),
            (
                "Worked with a team of 4 to ship a React dashboard",
                "Collaborated with 4 engineers to deliver a React dashboard",
            ),
            (
                "Wrote unit tests using pytest",
                "Authored pytest unit tests",
            ),
            (
                "Reduced page load time by 30% using caching",
                "Cut page load time 30% through caching",
            ),
            (
                "Automated deployment with Docker and GitHub Actions",
                "Owned Docker and GitHub Actions deployment automation",
            ),
        ],
    )
    def test_a_faithful_rephrasing_passes(self, source: str, rewrite: str) -> None:
        result = validate_rewrite(source, rewrite)
        assert result.ok, f"rejected a legitimate rewrite: {result.reason} {result.detail}"

    def test_reordering_passes(self) -> None:
        result = validate_rewrite(
            "Used Python and SQL to analyse survey data",
            "Analysed survey data with SQL and Python",
        )
        assert result.ok

    def test_dropping_a_claim_passes(self) -> None:
        """A rewrite may say less. Emphasis is a permitted transformation."""
        result = validate_rewrite(
            "Built a Python and Django service with PostgreSQL",
            "Built a Python service",
        )
        assert result.ok


class TestFabricationIsRejected:
    def test_an_added_technology_is_rejected(self) -> None:
        result = validate_rewrite(
            "Built a REST API in Python",
            "Built a REST API in Python deployed on Kubernetes",
        )
        assert not result.ok
        assert result.reason == RejectionReason.ADDED_TECHNOLOGY
        assert "Kubernetes" in result.detail

    def test_an_added_metric_is_rejected(self) -> None:
        """The most dangerous fabrication: unfalsifiable and unforgettable."""
        result = validate_rewrite(
            "Improved the checkout flow",
            "Improved the checkout flow, increasing conversion by 25%",
        )
        assert not result.ok
        assert result.reason == RejectionReason.ADDED_NUMBER

    def test_an_inflated_metric_is_rejected(self) -> None:
        result = validate_rewrite(
            "Reduced latency by 30%",
            "Reduced latency by 60%",
        )
        assert not result.ok
        assert result.reason == RejectionReason.ADDED_NUMBER

    def test_an_added_employer_is_rejected(self) -> None:
        result = validate_rewrite(
            "Interned on the platform team",
            "Interned on the platform team at Stripe",
        )
        assert not result.ok
        assert result.reason == RejectionReason.ADDED_PROPER_NOUN

    def test_an_added_team_size_is_rejected(self) -> None:
        result = validate_rewrite(
            "Led a project to migrate the database",
            "Led a team of 6 to migrate the database",
        )
        assert not result.ok

    def test_a_technology_from_a_different_bullet_is_rejected(self) -> None:
        """Validation is per bullet against its own source, for exactly this case.

        The student does know Python. They did not use it in the retail job, and a resume that
        says they did is false about that role — which is what an interviewer would find.
        """
        result = validate_rewrite(
            "Served customers at the till and handled cash reconciliation",
            "Automated cash reconciliation with Python",
        )
        assert not result.ok
        assert result.reason == RejectionReason.ADDED_TECHNOLOGY


class TestNumberNormalisation:
    @pytest.mark.parametrize(
        ("written", "expected"),
        [("40%", 40.0), ("40 percent", 40.0), ("forty percent", 40.0), ("1,200", 1200.0)],
    )
    def test_the_same_quantity_written_differently_is_one_value(
        self, written: str, expected: float
    ) -> None:
        assert normalise_number(written) == expected

    def test_a_metric_restated_in_words_passes(self) -> None:
        """A rewrite legitimately changes the form of a number it did not invent."""
        result = validate_rewrite(
            "Cut build time by 40%",
            "Cut build time by forty percent",
        )
        assert result.ok

    def test_a_year_is_not_treated_as_a_metric(self) -> None:
        """Dates are stored as written, and keeping one asserts no new quantity."""
        result = validate_rewrite(
            "Summer 2025 internship on the data team",
            "Data team internship, Summer 2025",
        )
        assert result.ok


class TestClaimExtraction:
    def test_technologies_are_found_by_the_shared_vocabulary(self) -> None:
        claims = extract_claims("Built a Python service with FastAPI and PostgreSQL")
        assert "Python" in claims.technologies
        assert "FastAPI" in claims.technologies
        assert "PostgreSQL" in claims.technologies

    def test_ordinary_capitalised_words_at_the_start_are_not_proper_nouns(self) -> None:
        """Every bullet begins with a capital. Treating that as an employer would reject all."""
        claims = extract_claims("Managed the release process")
        assert claims.proper_nouns == set()

    def test_a_real_proper_noun_is_found(self) -> None:
        claims = extract_claims("Interned at Shopify on the payments team")
        assert "Shopify" in claims.proper_nouns

    def test_numbers_are_extracted(self) -> None:
        claims = extract_claims("Handled 1,200 tickets and cut response time by 15%")
        assert 1200.0 in claims.numbers
        assert 15.0 in claims.numbers


class TestEdges:
    def test_an_empty_rewrite_is_rejected(self) -> None:
        result = validate_rewrite("Built a Python API", "")
        assert not result.ok
        assert result.reason == RejectionReason.EMPTY

    def test_an_identical_rewrite_passes(self) -> None:
        assert validate_rewrite("Built a Python API", "Built a Python API").ok

    def test_whitespace_differences_do_not_matter(self) -> None:
        assert validate_rewrite("Built a Python API", "  Built a  Python   API  ").ok

    def test_a_rewrite_far_longer_than_its_source_is_rejected(self) -> None:
        """Length is a proxy for invention even when every claim happens to check out.

        A bullet that triples in length has had prose added, and prose about work the student did
        not describe is a claim whatever it contains.
        """
        result = validate_rewrite(
            "Built an API",
            "Built an API, which involved extensive collaboration with senior stakeholders "
            "across multiple departments, delivering measurable business value and "
            "demonstrating exceptional ownership throughout the entire project lifecycle",
        )
        assert not result.ok
        assert result.reason == RejectionReason.TOO_LONG
