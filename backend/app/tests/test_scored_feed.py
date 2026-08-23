"""Score persistence, invalidation, and the scored feed.

The properties that matter here are about not lying to the student and not being expensive:
scores must not be recomputed on every render, must not survive the resume that produced them,
and must never be required for the feed to work at all.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board_token import BoardToken
from app.models.job import Job
from app.models.match_score import MatchScore
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.user import User
from app.security import create_access_token, hash_password
from app.services.scoring_service import get_student_profile, score_page

PARSED = {
    "summary": "Graduate developer",
    "skills": ["Python", "SQL", "Docker"],
    "experience": [{"id": "e1", "employer": "Lab", "title": "Intern", "dates": "2025", "bullets": []}],
    "education": [],
    "raw_text": "Python SQL Docker FastAPI PostgreSQL student projects",
}


async def _student_with_resume(session: AsyncSession) -> tuple[Student, ResumeMaster, str]:
    user = User(email="scored@example.test", password_hash=hash_password("Passw0rd!x"))
    session.add(user)
    await session.flush()

    student = Student(user_id=user.id, name="Scored Student")
    session.add(student)
    await session.flush()

    resume = ResumeMaster(
        student_id=student.id,
        version=1,
        filename="r.pdf",
        byte_size=10,
        pdf_bytes=b"%PDF-1.4",
        parsed_json=PARSED,
        is_active=True,
    )
    session.add(resume)
    await session.flush()
    return student, resume, create_access_token(user.id)


async def _job(session: AsyncSession, *, job_id: str, title: str, description: str) -> Job:
    board = (await session.execute(select(BoardToken).limit(1))).scalars().first()
    if board is None:
        board = BoardToken(
            provider="greenhouse", token="scoreco", company_name="ScoreCo", active=True
        )
        session.add(board)
        await session.flush()

    job = Job(
        source="greenhouse",
        source_job_id=job_id,
        board_token_id=board.id,
        company_name="ScoreCo",
        title=title,
        location_raw="Toronto, ON",
        country="CA",
        description=description,
        apply_url=f"https://example.test/{job_id}",
        seniority="entry",
        role_family="software_engineering",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job


class TestPersistence:
    async def test_a_score_is_stored_once_and_reused(self, session: AsyncSession) -> None:
        student, resume, _ = await _student_with_resume(session)
        job = await _job(
            session, job_id="1", title="Software Engineer", description="Python and SQL work."
        )
        profile = await get_student_profile(session, student.id)
        assert profile is not None

        first = await score_page(
            session,
            student_id=student.id,
            resume_master_id=resume.id,
            jobs=[job],
            profile=profile,
        )
        count_after_first = (
            await session.execute(select(func.count()).select_from(MatchScore))
        ).scalar()

        second = await score_page(
            session,
            student_id=student.id,
            resume_master_id=resume.id,
            jobs=[job],
            profile=profile,
        )
        count_after_second = (
            await session.execute(select(func.count()).select_from(MatchScore))
        ).scalar()

        assert count_after_first == 1
        assert count_after_second == 1, "a second render must not insert another row"
        assert first[job.id].total == second[job.id].total

    async def test_a_new_resume_produces_new_scores(self, session: AsyncSession) -> None:
        """Invalidation is free because the resume version is part of the identity."""
        student, resume, _ = await _student_with_resume(session)
        job = await _job(session, job_id="1", title="Engineer", description="Python work.")
        profile = await get_student_profile(session, student.id)
        assert profile is not None

        await score_page(
            session,
            student_id=student.id,
            resume_master_id=resume.id,
            jobs=[job],
            profile=profile,
        )

        newer = ResumeMaster(
            student_id=student.id,
            version=2,
            filename="r2.pdf",
            byte_size=10,
            pdf_bytes=b"%PDF-1.4",
            parsed_json=PARSED,
            is_active=True,
        )
        resume.is_active = False
        session.add(newer)
        await session.flush()

        await score_page(
            session,
            student_id=student.id,
            resume_master_id=newer.id,
            jobs=[job],
            profile=profile,
        )

        rows = (await session.execute(select(MatchScore))).scalars().all()
        assert len(rows) == 2, "the old score is kept, still true about the resume it describes"
        assert {r.resume_master_id for r in rows} == {resume.id, newer.id}

    async def test_the_stored_breakdown_survives_the_round_trip(
        self, session: AsyncSession
    ) -> None:
        student, resume, _ = await _student_with_resume(session)
        job = await _job(
            session,
            job_id="1",
            title="Engineer",
            description="You need Python, SQL and Kubernetes. 5+ years of experience required.",
        )
        profile = await get_student_profile(session, student.id)
        assert profile is not None

        computed = await score_page(
            session,
            student_id=student.id,
            resume_master_id=resume.id,
            jobs=[job],
            profile=profile,
        )
        session.expunge_all()
        reread = await score_page(
            session,
            student_id=student.id,
            resume_master_id=resume.id,
            jobs=[(await session.execute(select(Job).where(Job.id == job.id))).scalars().one()],
            profile=profile,
        )

        original = computed[job.id]
        stored = reread[job.id]
        assert stored.total == original.total
        assert stored.matched_skills == original.matched_skills
        assert stored.missing_skills == original.missing_skills
        assert stored.required_years == original.required_years
        assert stored.requirement_phrase == original.requirement_phrase


class TestTheFeed:
    async def test_the_feed_works_without_a_token(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The index is public. Requiring an account to browse would break the demo."""
        await _job(session, job_id="1", title="Engineer", description="Python.")
        await session.commit()

        response = await client.get("/api/v1/jobs")

        assert response.status_code == 200
        body = response.json()
        assert body["scored"] is False
        assert body["items"][0]["score"] is None

    async def test_an_authenticated_request_gets_scores(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _student_with_resume(session)
        await _job(
            session, job_id="1", title="Engineer", description="Python and SQL and Docker."
        )
        await session.commit()

        response = await client.get(
            "/api/v1/jobs", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["scored"] is True
        score = body["items"][0]["score"]
        assert score is not None
        assert (
            score["skill_points"]
            + score["experience_points"]
            + score["keyword_points"]
            + score["freshness_points"]
            == score["total"]
        ), "the parts a student reads must equal the total they read"

    async def test_a_student_without_a_resume_still_sees_the_feed(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = User(email="noresume@example.test", password_hash=hash_password("Passw0rd!x"))
        session.add(user)
        await session.flush()
        session.add(Student(user_id=user.id, name="No Resume"))
        await _job(session, job_id="1", title="Engineer", description="Python.")
        await session.commit()

        response = await client.get(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["scored"] is False, "the interface explains what uploading would add"
        assert len(body["items"]) == 1

    async def test_the_feed_is_ordered_by_score(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _student_with_resume(session)
        # A strong match and a weak one, inserted worst-first so recency ordering would invert.
        await _job(
            session,
            job_id="weak",
            title="Engineer",
            description="You will use Haskell and Erlang. 8+ years of experience required.",
        )
        await _job(
            session,
            job_id="strong",
            title="Engineer",
            description="You will use Python, SQL and Docker. No experience required.",
        )
        await session.commit()

        response = await client.get(
            "/api/v1/jobs", headers={"Authorization": f"Bearer {token}"}
        )

        items = response.json()["items"]
        assert len(items) == 2
        assert items[0]["score"]["total"] > items[1]["score"]["total"]
        assert items[0]["id"] != items[1]["id"]

    async def test_nothing_is_hidden_by_a_low_score(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """ADR 0003 rejected the 60-point cutoff, and it stays rejected."""
        _, _, token = await _student_with_resume(session)
        await _job(
            session,
            job_id="hopeless",
            title="Chief Actuary",
            description="You will need 20+ years of actuarial experience and a fellowship.",
        )
        await session.commit()

        response = await client.get(
            "/api/v1/jobs", headers={"Authorization": f"Bearer {token}"}
        )

        body = response.json()
        assert body["total"] == 1, "a student whose profile scores badly needs to see that"
        assert body["items"][0]["score"]["total"] < 50

    async def test_a_closed_posting_is_still_excluded_when_scored(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _student_with_resume(session)
        job = await _job(session, job_id="1", title="Engineer", description="Python.")
        job.closed_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

        response = await client.get(
            "/api/v1/jobs", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.json()["total"] == 0
