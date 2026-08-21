"""Reading the experience a posting demands.

This carries 30 of the 100 points and earns it: "5+ years required" is the most common reason a
graduate's application is discarded, and it is invisible from the title — a posting called
`Software Engineer` with five years in the body passes every filter feature 02 has.

Both directions of error cost something specific. Reading a preference as a requirement makes
the
feed pessimistic and buries workable jobs. Missing a real requirement puts the student's evening
into an application that was never going to be read.
"""

import pytest

from app.domain.experience import Basis, parse_experience_requirement


def _years(title: str, description: str) -> float | None:
    return parse_experience_requirement(title, description).years


class TestPlainRequirements:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("5+ years of experience required", 5),
            ("Minimum 3 years of experience", 3),
            ("At least 4 years of professional experience", 4),
            ("3-5 years of relevant experience", 3),
            ("2 to 4 years of experience", 2),
            ("Requires 7 years experience", 7),
            ("10+ years of industry experience", 10),
            ("18 months of experience", 1.5),
        ],
    )
    def test_a_stated_requirement_is_read(self, text: str, expected: float) -> None:
        assert _years("Engineer", text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Three years of experience required", 3),
            ("A minimum of five years of experience", 5),
            ("Two years' experience in a similar role", 2),
        ],
    )
    def test_written_numbers_are_read(self, text: str, expected: float) -> None:
        """Providers write this every way English allows."""
        assert _years("Engineer", text) == expected

    def test_the_requirement_is_found_in_the_title_too(self) -> None:
        assert _years("Software Engineer (5+ yrs)", "Join our team.") == 5


class TestPreferenceIsNotRequirement:
    @pytest.mark.parametrize(
        "text",
        [
            "3+ years preferred",
            "5 years of experience is a plus",
            "Ideally 4 years of experience",
            "2 years of experience nice to have",
            "Bonus: 3 years working with distributed systems",
        ],
    )
    def test_a_preference_is_recorded_as_a_preference(self, text: str) -> None:
        """A graduate may still be competitive, so this must not read as a hard bar."""
        result = parse_experience_requirement("Engineer", text)
        assert result.basis == Basis.PREFERRED, f"{text!r} read as {result.basis}"
        assert result.years is not None

    def test_a_requirement_wins_over_a_preference_in_the_same_text(self) -> None:
        result = parse_experience_requirement(
            "Engineer", "2+ years required. 5+ years preferred."
        )
        assert result.basis == Basis.REQUIRED
        assert result.years == 2, "the lower number is the bar the student must clear"

    def test_a_heading_carries_the_basis_for_the_lines_under_it(self) -> None:
        """Real descriptions put the basis in the heading, not in the bullet."""
        description = """
        Nice to have
        - 3+ years of experience with Kubernetes
        - Familiarity with Terraform
        """
        result = parse_experience_requirement("Platform Engineer", description)
        assert result.basis == Basis.PREFERRED, (
            "a bullet under 'Nice to have' is optional, and reading it as a bar hides a job "
            "a graduate could get"
        )

    def test_a_distant_heading_does_not_reach(self) -> None:
        """A heading twenty bullets above is no longer describing this line."""
        description = (
            "Nice to have\n"
            + "".join(f"- Some other item number {i}\n" for i in range(12))
            + "Requirements\n- 4 years of professional experience\n"
        )
        result = parse_experience_requirement("Engineer", description)
        assert result.basis == Basis.REQUIRED


class TestThingsThatAreNotDurations:
    @pytest.mark.parametrize(
        "text",
        [
            "Bachelor's degree (4 years)",
            "A 4-year degree in Computer Science",
            "4 year degree required",
        ],
    )
    def test_a_programme_length_demands_no_work_experience(self, text: str) -> None:
        assert _years("Engineer", text) is None

    @pytest.mark.parametrize(
        "text",
        [
            "Graduating in 2026",
            "Class of 2025 welcome",
            "Founded in 2015, we now serve millions",
            "Since 2019 we have grown steadily",
            "Summer 2026 start date",
        ],
    )
    def test_a_year_is_not_a_duration(self, text: str) -> None:
        assert _years("Engineer", text) is None

    @pytest.mark.parametrize(
        "text",
        [
            "Must be 18 years of age or older",
            "At least 18 years of age",
            "Must be at least 18 years old",
            "Applicants must be 19 years or older in Alberta",
            "You must have reached the legal working age of 16 years",
        ],
    )
    def test_an_age_is_not_experience(self, text: str) -> None:
        """Found in the real index: 31 postings appeared to demand eighteen years of experience.

        They were `Patient Care Coordinator`, `Customer Service Representative` and `PCA/HHA` —
        the most accessible jobs in the whole index — and the bug buried them at the bottom of
        the feed for exactly the reader this product is built for. The phrase carries every
        marker a genuine requirement has: "at least", a number, and the word years.
        """
        result = parse_experience_requirement("Customer Service Representative", text)
        assert result.years is None, f"{text!r} produced {result.years}"

    def test_an_age_boilerplate_does_not_hide_a_real_requirement(self) -> None:
        """The guard must reject the age and still find the actual bar."""
        description = """
        Requirements
        - Must be 18 years of age or older
        - 2+ years of experience in a customer-facing role
        """
        result = parse_experience_requirement("Customer Service Representative", description)
        assert result.years == 2

    @pytest.mark.parametrize(
        "text",
        [
            "$120,000 per year",
            "Salary of 95000 per year",
            "40 hours per week",
            "Revenue grew 30% year over year",
            "20 days of paid time off per year",
            "3 years of tenure is our average",
        ],
    )
    def test_money_hours_and_metrics_are_not_requirements(self, text: str) -> None:
        result = parse_experience_requirement("Engineer", text)
        assert result.years is None, f"{text!r} produced {result.years}"


class TestExplicitZero:
    @pytest.mark.parametrize(
        "text",
        [
            "0-2 years of experience",
            "No experience required",
            "New graduates welcome",
            "This is an entry level position",
            "0+ years of experience",
        ],
    )
    def test_an_explicit_zero_is_not_silence(self, text: str) -> None:
        result = parse_experience_requirement("Engineer", text)
        assert result.years == 0
        assert result.basis != Basis.UNSTATED, "the posting did say something"


class TestUnstated:
    def test_nothing_found_is_unstated_rather_than_zero(self) -> None:
        """A description that never mentions experience has not said the student qualifies."""
        result = parse_experience_requirement(
            "Software Engineer",
            "You will build features, review code, and work with a small team.",
        )
        assert result.basis == Basis.UNSTATED
        assert result.years is None

    def test_empty_input_is_unstated(self) -> None:
        result = parse_experience_requirement("", "")
        assert result.basis == Basis.UNSTATED
        assert result.years is None


class TestBasisIsShown:
    def test_the_matched_phrase_is_returned(self) -> None:
        """The interface shows the words it read, not only the number it produced."""
        result = parse_experience_requirement(
            "Engineer", "We need 5+ years of experience with Python."
        )
        assert result.phrase is not None
        assert "5+ years" in result.phrase

    def test_the_phrase_is_short_enough_to_display(self) -> None:
        long_text = "Filler. " * 200 + "Requires 3 years of experience. " + "More. " * 200
        result = parse_experience_requirement("Engineer", long_text)
        assert result.phrase is not None
        assert len(result.phrase) <= 120


class TestRealisticDescriptions:
    def test_a_graduate_posting_with_a_hidden_requirement(self) -> None:
        """What this component is for: the title says nothing, the body says five years."""
        description = """
        About the role
        We are looking for a Software Engineer to join our platform team.

        What you will do
        - Build and operate services used across the company
        - Partner with product and design

        What we are looking for
        - 5+ years of experience building production software
        - Strong knowledge of a modern backend language
        """
        result = parse_experience_requirement("Software Engineer", description)
        assert result.years == 5
        assert result.basis == Basis.REQUIRED

    def test_a_genuine_graduate_posting(self) -> None:
        description = """
        New Grad Software Engineer, 2026

        We hire people at the start of their careers. No prior industry
        experience is required. You should be graduating in 2026.
        """
        result = parse_experience_requirement("New Grad Software Engineer", description)
        assert result.years == 0
        assert result.basis != Basis.UNSTATED

    def test_the_salary_paragraph_does_not_become_a_requirement(self) -> None:
        description = """
        What we are looking for
        - Curiosity and a bias to action

        Compensation
        The base salary range for this role is $120,000 - $150,000 per year.
        We also offer 20 days of vacation per year.
        """
        assert _years("Engineer", description) is None
