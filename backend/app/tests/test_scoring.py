"""The four components and their arithmetic.

Two properties are load-bearing and easy to get subtly wrong:

- **The parts must sum to the total exactly.** A student who reads the segments and the total and
  finds them a point apart has no way to read that as anything but a bug, and no reason to trust
  anything else the product says.
- **Unstated must never score as zero.** Zero ranks a description that omitted its requirements
  below one stating requirements the student fails, which is backwards.
"""

from datetime import UTC, datetime, timedelta

from app.domain.experience import Basis, ExperienceRequirement
from app.domain.scoring import (
    FRESHNESS_WEIGHT,
    KEYWORD_WEIGHT,
    SKILL_WEIGHT,
    ComponentState,
    MatchBreakdown,
    StudentProfile,
    score_job,
)

NOW = datetime(2026, 8, 20, tzinfo=UTC)


def _profile(
    skills: set[str] | None = None, *, years: float = 0.0, resume_text: str = ""
) -> StudentProfile:
    return StudentProfile(
        skills=skills if skills is not None else {"Python", "SQL", "Docker"},
        years_experience=years,
        resume_text=resume_text or "Python SQL Docker student projects",
    )


# A sentinel, because `posted_at=None` is a meaningful value here — providers omit the date — and
# a default of NOW would silently swallow the case the test is about.
_DEFAULT = object()


def _posting(
    *,
    skills: set[str] | None = None,
    requirement: ExperienceRequirement | None = None,
    description: str = "We want a Python engineer who knows SQL.",
    posted_at: datetime | None | object = _DEFAULT,
) -> dict[str, object]:
    return {
        "skills": skills if skills is not None else {"Python", "SQL"},
        "requirement": requirement or ExperienceRequirement(None, Basis.UNSTATED),
        "description": description,
        "posted_at": NOW if posted_at is _DEFAULT else posted_at,
    }


def _score(profile: StudentProfile, posting: dict[str, object]) -> MatchBreakdown:
    return score_job(
        profile,
        posting_skills=posting["skills"],  # type: ignore[arg-type]
        requirement=posting["requirement"],  # type: ignore[arg-type]
        description=posting["description"],  # type: ignore[arg-type]
        posted_at=posting["posted_at"],  # type: ignore[arg-type]
        now=NOW,
    )


class TestTheSumIsExact:
    def test_the_parts_equal_the_total(self) -> None:
        result = _score(_profile(), _posting())
        assert (
            result.skill_points
            + result.experience_points
            + result.keyword_points
            + result.freshness_points
            == result.total
        )

    def test_the_total_is_never_out_of_range(self) -> None:
        perfect = _score(
            _profile({"Python", "SQL"}),
            _posting(requirement=ExperienceRequirement(0, Basis.REQUIRED)),
        )
        assert 0 <= perfect.total <= 100

    def test_every_component_stays_inside_its_weight(self) -> None:
        result = _score(_profile(), _posting())
        assert 0 <= result.skill_points <= SKILL_WEIGHT
        assert 0 <= result.experience_points <= 30
        assert 0 <= result.keyword_points <= KEYWORD_WEIGHT
        assert 0 <= result.freshness_points <= FRESHNESS_WEIGHT

    def test_all_components_are_integers(self) -> None:
        """Floats here are how the visible parts end up a point away from the visible total."""
        result = _score(_profile(), _posting())
        for value in (
            result.skill_points,
            result.experience_points,
            result.keyword_points,
            result.freshness_points,
            result.total,
        ):
            assert isinstance(value, int)


class TestSkillComponent:
    def test_every_required_skill_present_scores_full_marks(self) -> None:
        result = _score(_profile({"Python", "SQL", "Docker"}), _posting(skills={"Python", "SQL"}))
        assert result.skill_points == SKILL_WEIGHT

    def test_no_overlap_scores_zero(self) -> None:
        result = _score(_profile({"Excel"}), _posting(skills={"Python", "SQL"}))
        assert result.skill_points == 0

    def test_half_the_skills_scores_about_half(self) -> None:
        result = _score(_profile({"Python"}), _posting(skills={"Python", "SQL"}))
        assert result.skill_points == SKILL_WEIGHT // 2

    def test_a_posting_that_lists_no_skills_is_not_scored_zero(self) -> None:
        """Zero would rank an uninformative posting below one the student genuinely fails."""
        result = _score(_profile(), _posting(skills=set()))
        assert result.skill_points > 0
        assert result.skill_state == ComponentState.UNSTATED

    def test_the_matched_and_missing_skills_are_reported(self) -> None:
        result = _score(
            _profile({"Python"}), _posting(skills={"Python", "SQL", "Kubernetes"})
        )
        assert result.matched_skills == ["Python"]
        assert result.missing_skills == ["Kubernetes", "SQL"], "sorted, so the display is stable"

    def test_extra_profile_skills_do_not_raise_the_score(self) -> None:
        """The question is what the posting wants, not how much the student knows."""
        few = _score(_profile({"Python", "SQL"}), _posting(skills={"Python", "SQL"}))
        many = _score(
            _profile({"Python", "SQL", "Go", "Rust", "AWS"}), _posting(skills={"Python", "SQL"})
        )
        assert few.skill_points == many.skill_points

    def test_the_score_does_not_depend_on_skill_ordering(self) -> None:
        a = _score(_profile({"Python", "SQL"}), _posting(skills={"SQL", "Python"}))
        b = _score(_profile({"SQL", "Python"}), _posting(skills={"Python", "SQL"}))
        assert a.total == b.total


class TestExperienceComponent:
    def test_a_met_requirement_scores_full_marks(self) -> None:
        result = _score(
            _profile(years=2),
            _posting(requirement=ExperienceRequirement(2, Basis.REQUIRED)),
        )
        assert result.experience_points == 30
        assert result.experience_state == ComponentState.MET

    def test_a_zero_requirement_is_met_by_a_graduate(self) -> None:
        result = _score(
            _profile(years=0), _posting(requirement=ExperienceRequirement(0, Basis.REQUIRED))
        )
        assert result.experience_points == 30

    def test_the_score_tapers_as_the_gap_grows(self) -> None:
        gaps = [
            _score(
                _profile(years=0),
                _posting(requirement=ExperienceRequirement(years, Basis.REQUIRED)),
            ).experience_points
            for years in (1, 2, 3, 5, 8, 10)
        ]
        assert gaps == sorted(gaps, reverse=True), f"not monotonic: {gaps}"
        assert gaps[0] > gaps[-1]

    def test_a_large_gap_is_not_negative(self) -> None:
        result = _score(
            _profile(years=0),
            _posting(requirement=ExperienceRequirement(25, Basis.REQUIRED)),
        )
        assert result.experience_points == 0

    def test_an_unstated_requirement_is_neutral_and_labelled(self) -> None:
        result = _score(
            _profile(years=0), _posting(requirement=ExperienceRequirement(None, Basis.UNSTATED))
        )
        assert result.experience_state == ComponentState.UNSTATED
        assert 0 < result.experience_points < 30, "neutral, not full marks and not zero"

    def test_a_preference_costs_less_than_a_requirement(self) -> None:
        """A graduate may still be competitive against a preference."""
        preferred = _score(
            _profile(years=0),
            _posting(requirement=ExperienceRequirement(5, Basis.PREFERRED)),
        )
        required = _score(
            _profile(years=0),
            _posting(requirement=ExperienceRequirement(5, Basis.REQUIRED)),
        )
        assert preferred.experience_points > required.experience_points


class TestKeywordComponent:
    def test_a_description_sharing_the_resume_vocabulary_scores_higher(self) -> None:
        close = _score(
            _profile(resume_text="Python FastAPI PostgreSQL Docker testing"),
            _posting(description="You will write Python with FastAPI and PostgreSQL in Docker."),
        )
        far = _score(
            _profile(resume_text="Python FastAPI PostgreSQL Docker testing"),
            _posting(description="You will manage vendor contracts and negotiate leases."),
        )
        assert close.keyword_points > far.keyword_points

    def test_an_empty_description_does_not_crash(self) -> None:
        result = _score(_profile(), _posting(description=""))
        assert result.keyword_points == 0

    def test_a_student_with_no_resume_text_scores_zero_keywords(self) -> None:
        result = _score(_profile(resume_text=" "), _posting())
        assert result.keyword_points == 0


class TestFreshnessComponent:
    def test_today_scores_full_marks(self) -> None:
        result = _score(_profile(), _posting(posted_at=NOW))
        assert result.freshness_points == FRESHNESS_WEIGHT

    def test_a_month_old_posting_scores_nothing(self) -> None:
        result = _score(_profile(), _posting(posted_at=NOW - timedelta(days=32)))
        assert result.freshness_points == 0

    def test_freshness_decreases_with_age(self) -> None:
        ages = [
            _score(_profile(), _posting(posted_at=NOW - timedelta(days=d))).freshness_points
            for d in (0, 3, 7, 14, 21, 30)
        ]
        assert ages == sorted(ages, reverse=True), f"not monotonic: {ages}"

    def test_an_unknown_posting_date_is_neutral_not_zero(self) -> None:
        """Providers frequently omit the date; the student is not at fault for that."""
        result = _score(_profile(), _posting(posted_at=None))
        assert result.freshness_points > 0
        assert result.freshness_state == ComponentState.UNSTATED

    def test_a_future_date_is_clamped(self) -> None:
        result = _score(_profile(), _posting(posted_at=NOW + timedelta(days=5)))
        assert result.freshness_points == FRESHNESS_WEIGHT


class TestNoResume:
    def test_a_student_without_a_resume_gets_an_incomplete_breakdown(self) -> None:
        result = score_job(
            None,
            posting_skills={"Python"},
            requirement=ExperienceRequirement(None, Basis.UNSTATED),
            description="Python work",
            posted_at=NOW,
            now=NOW,
        )
        assert result.is_complete is False
        assert result.total == 0, "no profile is not a score of zero merit, it is no score"

    def test_a_scored_student_is_complete(self) -> None:
        assert _score(_profile(), _posting()).is_complete is True


class TestDeterminism:
    def test_the_same_inputs_score_the_same_every_time(self) -> None:
        first = _score(_profile(), _posting())
        second = _score(_profile(), _posting())
        assert first == second

    def test_freshness_uses_the_injected_time_not_the_clock(self) -> None:
        """A score that moves because time passed is a score nobody can reproduce."""
        posting = _posting(posted_at=NOW - timedelta(days=5))
        a = _score(_profile(), posting)
        b = score_job(
            _profile(),
            posting_skills={"Python", "SQL"},
            requirement=ExperienceRequirement(None, Basis.UNSTATED),
            description="We want a Python engineer who knows SQL.",
            posted_at=NOW - timedelta(days=5),
            now=NOW,
        )
        assert a.freshness_points == b.freshness_points
