"""The score has to be checkable, not merely displayed.

ADR 0003 chose deterministic scoring over asking a model, and the reason was auditability: a
student can be shown the arithmetic and catch Reachly being wrong. That promise is only kept if the
explanation and the score are the same calculation, so the property tested hardest here is that
they cannot disagree.

The rest assert properties rather than answers — the parts sum to the whole, no component exceeds
its weight, an unknown is worth half and never zero, and every word claimed as shared is genuinely
in both documents. Fixed expected totals would pin the tests to today's weights and would have to
be rewritten the first time ADR 0003 is amended, which is exactly when they most need to still work.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.experience import Basis, ExperienceRequirement
from app.domain.scoring import (
    ComponentState,
    StudentProfile,
    explain_score,
    score_job,
)
from app.models.board_token import BoardToken
from app.models.job import Job
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.user import User
from app.security import create_access_token, hash_password

NOW = datetime(2026, 8, 23, tzinfo=UTC)

PROFILE = StudentProfile(
    skills={"Python", "SQL", "Docker"},
    years_experience=1.0,
    resume_text="Python SQL Docker FastAPI PostgreSQL pytest graduate projects",
)


def _requirement(
    years: float | None, basis: Basis, phrase: str | None = None
) -> ExperienceRequirement:
    return ExperienceRequirement(years=years, basis=basis, phrase=phrase)


class TestTheExplanationAgreesWithTheScore:
    """If these two ever diverge, the product is lying in the place it promised not to."""

    def test_the_total_matches_the_scorer_on_the_same_inputs(self) -> None:
        cases = [
            ({"Python", "Kubernetes"}, _requirement(3, Basis.REQUIRED, "3+ years required")),
            ({"Python", "SQL", "Docker"}, _requirement(None, Basis.UNSTATED)),
            (set(), _requirement(1, Basis.PREFERRED, "1 year preferred")),
            ({"Rust", "Erlang", "Haskell"}, _requirement(12, Basis.REQUIRED, "12+ years")),
        ]

        for posting_skills, requirement in cases:
            description = "We want " + ", ".join(sorted(posting_skills) or ["nothing specific"])
            scored = score_job(
                PROFILE,
                posting_skills=posting_skills,
                requirement=requirement,
                description=description,
                posted_at=NOW - timedelta(days=3),
                now=NOW,
            )
            explained = explain_score(
                PROFILE,
                posting_skills=posting_skills,
                requirement=requirement,
                description=description,
                posted_at=NOW - timedelta(days=3),
                now=NOW,
            )

            assert explained.total == scored.total, (
                f"explanation disagrees with the score for {posting_skills}: "
                f"{explained.total} vs {scored.total}"
            )
            assert explained.skill_points == scored.skill_points
            assert explained.experience_points == scored.experience_points
            assert explained.keyword_points == scored.keyword_points
            assert explained.freshness_points == scored.freshness_points

    def test_the_parts_sum_to_the_total(self) -> None:
        explained = explain_score(
            PROFILE,
            posting_skills={"Python", "Kubernetes"},
            requirement=_requirement(2, Basis.REQUIRED, "2+ years required"),
            description="Python and Kubernetes, 2+ years required.",
            posted_at=NOW - timedelta(days=1),
            now=NOW,
        )

        parts = (
            explained.skill_points
            + explained.experience_points
            + explained.keyword_points
            + explained.freshness_points
        )
        assert parts == explained.total, (
            "a student adding the visible parts must reach the total"
        )

    def test_no_component_can_exceed_its_own_weight(self) -> None:
        """A perfect match on every axis, which is where an off-by-one would show."""
        explained = explain_score(
            StudentProfile(
                skills={"Python"}, years_experience=40.0, resume_text="Python " * 50
            ),
            posting_skills={"Python"},
            requirement=_requirement(1, Basis.REQUIRED, "1 year required"),
            description="Python " * 50,
            posted_at=NOW,
            now=NOW,
        )

        assert explained.skill_points <= explained.skill_weight
        assert explained.experience_points <= explained.experience_weight
        assert explained.keyword_points <= explained.keyword_weight
        assert explained.freshness_points <= explained.freshness_weight


class TestTheDerivationIsHonest:
    def test_the_skills_denominator_is_what_the_posting_asked_for(self) -> None:
        """Not the student's skill count. The question is whether the job's needs are met."""
        explained = explain_score(
            PROFILE,
            posting_skills={"Python", "Kubernetes", "Terraform"},
            requirement=_requirement(None, Basis.UNSTATED),
            description="Python, Kubernetes, Terraform.",
            posted_at=NOW,
            now=NOW,
        )

        assert explained.skills_asked == 3
        assert len(explained.matched_skills) + len(explained.missing_skills) == 3
        assert "Python" in explained.matched_skills
        assert set(explained.missing_skills) == {"Kubernetes", "Terraform"}

    def test_every_shared_word_is_in_both_documents(self) -> None:
        """The keyword evidence must be checkable, or it is decoration."""
        description = "Build services in Python against PostgreSQL. Kubernetes and Terraform."
        explained = explain_score(
            PROFILE,
            posting_skills=set(),
            requirement=_requirement(None, Basis.UNSTATED),
            description=description,
            posted_at=NOW,
            now=NOW,
        )

        assert explained.shared_keywords, "the resume and posting plainly share vocabulary"
        resume_lower = PROFILE.resume_text.casefold()
        description_lower = description.casefold()
        for word in explained.shared_keywords:
            assert word in resume_lower, f"{word!r} claimed as shared but not in the resume"
            assert word in description_lower, (
                f"{word!r} claimed as shared but not in the posting"
            )

    def test_a_word_only_in_the_posting_is_not_claimed_as_shared(self) -> None:
        explained = explain_score(
            PROFILE,
            posting_skills=set(),
            requirement=_requirement(None, Basis.UNSTATED),
            description="Kubernetes Terraform Rust Erlang",
            posted_at=NOW,
            now=NOW,
        )

        assert "kubernetes" not in explained.shared_keywords
        assert "rust" not in explained.shared_keywords

    def test_an_unstated_requirement_is_worth_half_and_says_so(self) -> None:
        """Never zero. ADR 0003: a student can act on a stated mismatch, not on silence."""
        explained = explain_score(
            PROFILE,
            posting_skills={"Python"},
            requirement=_requirement(None, Basis.UNSTATED),
            description="Python role.",
            posted_at=NOW,
            now=NOW,
        )

        assert explained.experience_state is ComponentState.UNSTATED
        assert explained.experience_points == round(
            explained.experience_weight * explained.neutral_share
        )
        assert explained.experience_points > 0, "silence is not failure"
        assert explained.required_years is None

    def test_the_experience_derivation_carries_both_sides_of_the_comparison(self) -> None:
        """A student cannot check a subtraction they are only shown one side of."""
        explained = explain_score(
            PROFILE,
            posting_skills={"Python"},
            requirement=_requirement(5, Basis.REQUIRED, "5+ years of experience required"),
            description="Python role. 5+ years of experience required.",
            posted_at=NOW,
            now=NOW,
        )

        assert explained.required_years == 5
        assert explained.student_years == PROFILE.years_experience
        assert explained.requirement_phrase == "5+ years of experience required"
        assert explained.max_gap_years > 0
        assert explained.experience_state is ComponentState.SHORT

    def test_a_preference_scores_above_the_same_number_as_a_requirement(self) -> None:
        preferred = explain_score(
            PROFILE,
            posting_skills={"Python"},
            requirement=_requirement(6, Basis.PREFERRED, "6+ years preferred"),
            description="Python role.",
            posted_at=NOW,
            now=NOW,
        )
        required = explain_score(
            PROFILE,
            posting_skills={"Python"},
            requirement=_requirement(6, Basis.REQUIRED, "6+ years required"),
            description="Python role.",
            posted_at=NOW,
            now=NOW,
        )

        assert preferred.experience_points > required.experience_points
        # And neither may beat actually meeting the bar.
        met = explain_score(
            PROFILE,
            posting_skills={"Python"},
            requirement=_requirement(0.5, Basis.REQUIRED, "some experience"),
            description="Python role.",
            posted_at=NOW,
            now=NOW,
        )
        assert met.experience_points >= preferred.experience_points

    def test_freshness_reports_the_age_it_used(self) -> None:
        explained = explain_score(
            PROFILE,
            posting_skills={"Python"},
            requirement=_requirement(None, Basis.UNSTATED),
            description="Python role.",
            posted_at=NOW - timedelta(days=10),
            now=NOW,
        )

        assert explained.age_days is not None
        assert 9.9 < explained.age_days < 10.1
        assert explained.freshness_horizon_days > 0

    def test_a_posting_with_no_date_is_unstated_rather_than_stale(self) -> None:
        explained = explain_score(
            PROFILE,
            posting_skills={"Python"},
            requirement=_requirement(None, Basis.UNSTATED),
            description="Python role.",
            posted_at=None,
            now=NOW,
        )

        assert explained.freshness_state is ComponentState.UNSTATED
        assert explained.age_days is None
        assert explained.freshness_points > 0, "a missing date is the provider's fault"


PARSED = {
    "summary": "Graduate developer",
    "skills": ["Python", "SQL", "Docker"],
    "experience": [
        {"id": "e1", "employer": "Lab", "title": "Intern", "dates": "2025", "bullets": []}
    ],
    "education": [],
    "raw_text": "Python SQL Docker FastAPI PostgreSQL pytest",
}


async def _student_with_resume(session: AsyncSession) -> str:
    user = User(email="explain@example.test", password_hash=hash_password("Passw0rd!x"))
    session.add(user)
    await session.flush()
    student = Student(user_id=user.id, name="Explain Student")
    session.add(student)
    await session.flush()
    session.add(
        ResumeMaster(
            student_id=student.id,
            version=1,
            filename="r.pdf",
            byte_size=10,
            pdf_bytes=b"%PDF-1.4",
            parsed_json=PARSED,
            is_active=True,
        )
    )
    await session.flush()
    return create_access_token(user.id)


async def _job(session: AsyncSession, *, description: str) -> Job:
    board = (await session.execute(select(BoardToken).limit(1))).scalars().first()
    job = Job(
        board_token_id=board.id if board else None,
        source="greenhouse",
        source_job_id="explain-1",
        title="Backend Engineer",
        company_name="Acme",
        description=description,
        apply_url="https://example.test/apply",
        is_verified=True,
        first_seen_at=datetime.now(UTC) - timedelta(days=2),
        posted_at=datetime.now(UTC) - timedelta(days=2),
    )
    session.add(job)
    await session.flush()
    return job


class TestTheEndpoint:
    async def test_it_returns_every_component_with_its_weight(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token = await _student_with_resume(session)
        job = await _job(
            session,
            description="Python and PostgreSQL. Kubernetes required. 3+ years required.",
        )
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/score", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        body = response.json()
        names = [c["name"] for c in body["components"]]
        assert names == ["skills", "experience", "keywords", "freshness"]

        # The weights travel with the response so the interface never hardcodes them.
        assert sum(c["weight"] for c in body["components"]) == 100
        assert sum(c["points"] for c in body["components"]) == body["total"]
        for component in body["components"]:
            assert component["points"] <= component["weight"]

    async def test_it_names_the_gap_and_quotes_the_requirement(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token = await _student_with_resume(session)
        job = await _job(
            session,
            description="Python and PostgreSQL. Kubernetes required. 3+ years required.",
        )
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/score", headers={"Authorization": f"Bearer {token}"}
        )

        body = response.json()
        assert "Kubernetes" in body["missing_skills"]
        assert "Python" in body["matched_skills"]
        assert body["requirement_phrase"], "the number needs its sentence"

        experience = next(c for c in body["components"] if c["name"] == "experience")
        assert experience["facts"]["required_years"] == 3
        assert experience["facts"]["your_years"] is not None

    async def test_the_skills_facts_let_the_student_redo_the_division(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token = await _student_with_resume(session)
        job = await _job(session, description="Python, Docker, Kubernetes, Terraform.")
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/score", headers={"Authorization": f"Bearer {token}"}
        )

        body = response.json()
        skills = next(c for c in body["components"] if c["name"] == "skills")
        asked = skills["facts"]["asked"]
        matched = skills["facts"]["matched"]

        assert asked == len(body["matched_skills"]) + len(body["missing_skills"])
        assert matched == len(body["matched_skills"])
        assert skills["points"] == round(skills["weight"] * matched / asked)

    async def test_an_anonymous_reader_is_told_what_is_missing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        job = await _job(session, description="Python role.")
        await session.commit()

        response = await client.get(f"/api/v1/jobs/{job.id}/score")

        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "score_unavailable"
        assert "resume" in body["error"]["message"].lower()

    async def test_a_student_without_a_resume_is_told_why(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = User(
            email="noresume-explain@example.test", password_hash=hash_password("Passw0rd!x")
        )
        session.add(user)
        await session.flush()
        session.add(Student(user_id=user.id, name="No Resume"))
        job = await _job(session, description="Python role.")
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/score",
            headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "score_unavailable"

    async def test_the_explanation_matches_the_feed_for_the_same_posting(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The number on the card and the number on the report are one number.

        Worth an integration test rather than only a unit one, because the feed reads from the
        score cache and the explanation computes fresh. Those are two code paths to the same
        claim, and a student who sees 58 on the card and 61 on the report has caught the product
        contradicting itself.
        """
        token = await _student_with_resume(session)
        job = await _job(
            session,
            description="Python and PostgreSQL. Kubernetes required. 3+ years required.",
        )
        await session.commit()

        feed = await client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"})
        card = next(item for item in feed.json()["items"] if item["id"] == job.id)

        report = await client.get(
            f"/api/v1/jobs/{job.id}/score", headers={"Authorization": f"Bearer {token}"}
        )

        assert report.json()["total"] == card["score"]["total"]
