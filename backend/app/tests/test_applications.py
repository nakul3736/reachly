"""Application tracking.

The properties worth asserting are the ones that make the tracker trustworthy rather than convenient:
that a status is only ever what the student said, that reporting an application captures which resume
went out, and that one student cannot see or move another's pipeline.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory
from app.models.application import Application, ApplicationStatus
from app.models.board_token import BoardToken
from app.models.job import Job
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.tailored_resume import TailoredResume
from app.models.user import User
from app.security import create_access_token, hash_password

PARSED = {
    "summary": "Graduate",
    "skills": ["Python"],
    "experience": [],
    "projects": [],
    "education": [],
    "raw_text": "Python",
}


async def _student(session: AsyncSession, *, email: str = "track@example.test") -> tuple[str, int]:
    user = User(email=email, password_hash=hash_password("Passw0rd!x"))
    session.add(user)
    await session.flush()
    student = Student(user_id=user.id, name="Test Graduate")
    session.add(student)
    await session.flush()
    session.add(
        ResumeMaster(
            student_id=student.id,
            version=1,
            filename="r.pdf",
            byte_size=8,
            pdf_bytes=b"%PDF-1.4",
            parsed_json=PARSED,
            is_active=True,
        )
    )
    await session.flush()
    return create_access_token(user.id), student.id


async def _job(session: AsyncSession, *, source_job_id: str, company: str = "Acme") -> Job:
    board = (await session.execute(select(BoardToken).limit(1))).scalars().first()
    job = Job(
        board_token_id=board.id if board else None,
        source="greenhouse",
        source_job_id=source_job_id,
        title="Backend Engineer",
        company_name=company,
        description="Python required.",
        apply_url="https://example.test/apply",
        is_verified=True,
        first_seen_at=datetime.now(UTC) - timedelta(days=2),
        posted_at=datetime.now(UTC) - timedelta(days=2),
    )
    session.add(job)
    await session.flush()
    return job


class TestTrackingAPosting:
    async def test_saving_a_posting_starts_the_pipeline(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token, _ = await _student(session)
        job = await _job(session, source_job_id="t1")
        await session.commit()

        response = await client.post(
            "/api/v1/applications",
            json={"job_id": job.id},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "saved"
        assert body["applied_at"] is None, "saving is not applying"
        assert body["title"] == "Backend Engineer"

    async def test_tracking_the_same_posting_twice_updates_rather_than_duplicates(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token, _ = await _student(session)
        job = await _job(session, source_job_id="t2")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        first = await client.post("/api/v1/applications", json={"job_id": job.id}, headers=headers)
        second = await client.post(
            "/api/v1/applications",
            json={"job_id": job.id, "status": "applied"},
            headers=headers,
        )

        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["status"] == "applied"

        async with get_session_factory()() as other:
            rows = (
                (await other.execute(select(Application).where(Application.job_id == job.id)))
                .scalars()
                .all()
            )
        assert len(rows) == 1

    async def test_reporting_an_application_records_when_and_what_was_sent(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The pointer to the tailored resume is why this table exists rather than a bookmark list."""
        token, student_id = await _student(session)
        job = await _job(session, source_job_id="t3")
        tailored = TailoredResume(
            student_id=student_id,
            job_id=job.id,
            resume_master_id=(
                await session.execute(
                    select(ResumeMaster.id).where(ResumeMaster.student_id == student_id)
                )
            )
            .scalars()
            .first(),
            bullets=[],
            gaps=[],
        )
        session.add(tailored)
        await session.commit()

        response = await client.post(
            "/api/v1/applications",
            json={"job_id": job.id, "status": "applied"},
            headers={"Authorization": f"Bearer {token}"},
        )

        body = response.json()
        assert body["applied_at"] is not None
        assert body["tailored_resume_id"] == tailored.id
        assert body["has_tailored_resume"] is True

    async def test_applying_without_tailoring_is_recorded_honestly(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """A student may send their master resume. Claiming a tailored one would be a false answer."""
        token, _ = await _student(session)
        job = await _job(session, source_job_id="t4")
        await session.commit()

        response = await client.post(
            "/api/v1/applications",
            json={"job_id": job.id, "status": "applied"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.json()["tailored_resume_id"] is None
        assert response.json()["has_tailored_resume"] is False

    async def test_the_applied_date_is_not_moved_by_a_later_status_change(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token, _ = await _student(session)
        job = await _job(session, source_job_id="t5")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        applied = await client.post(
            "/api/v1/applications",
            json={"job_id": job.id, "status": "applied"},
            headers=headers,
        )
        first_date = applied.json()["applied_at"]

        moved = await client.patch(
            f"/api/v1/applications/{applied.json()['id']}",
            json={"status": "interviewing"},
            headers=headers,
        )
        back = await client.patch(
            f"/api/v1/applications/{applied.json()['id']}",
            json={"status": "applied"},
            headers=headers,
        )

        assert moved.json()["applied_at"] == first_date
        assert back.json()["applied_at"] == first_date, "the date it happened does not change"


class TestThePipelineView:
    async def test_it_counts_every_status_including_the_empty_ones(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """So the interface renders stable columns rather than ones that appear and vanish."""
        token, _ = await _student(session)
        saved = await _job(session, source_job_id="p1")
        applied = await _job(session, source_job_id="p2")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/applications", json={"job_id": saved.id}, headers=headers)
        await client.post(
            "/api/v1/applications",
            json={"job_id": applied.id, "status": "applied"},
            headers=headers,
        )

        response = await client.get("/api/v1/applications", headers=headers)

        counts = response.json()["counts"]
        assert counts["saved"] == 1
        assert counts["applied"] == 1
        assert counts["interviewing"] == 0
        assert counts["offer"] == 0
        assert counts["rejected"] == 0
        assert counts["withdrawn"] == 0
        assert set(counts) == {s.value for s in ApplicationStatus}

    async def test_a_posting_taken_down_is_flagged_not_hidden(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """A closed posting with an outstanding application is information, not clutter."""
        token, _ = await _student(session)
        job = await _job(session, source_job_id="p3")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.post(
            "/api/v1/applications", json={"job_id": job.id, "status": "applied"}, headers=headers
        )

        job.closed_at = datetime.now(UTC)
        await session.commit()

        response = await client.get("/api/v1/applications", headers=headers)

        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["closed"] is True

    async def test_notes_survive_a_status_change(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token, _ = await _student(session)
        job = await _job(session, source_job_id="p4")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        created = await client.post(
            "/api/v1/applications", json={"job_id": job.id}, headers=headers
        )
        await client.patch(
            f"/api/v1/applications/{created.json()['id']}",
            json={"notes": "Spoke to Priya on the platform team."},
            headers=headers,
        )
        moved = await client.patch(
            f"/api/v1/applications/{created.json()['id']}",
            json={"status": "interviewing"},
            headers=headers,
        )

        assert moved.json()["notes"] == "Spoke to Priya on the platform team."


class TestOnePipelinePerStudent:
    async def test_another_student_cannot_see_it(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mine, _ = await _student(session, email="mine@example.test")
        theirs, _ = await _student(session, email="theirs@example.test")
        job = await _job(session, source_job_id="s1")
        await session.commit()

        await client.post(
            "/api/v1/applications",
            json={"job_id": job.id},
            headers={"Authorization": f"Bearer {mine}"},
        )

        response = await client.get(
            "/api/v1/applications", headers={"Authorization": f"Bearer {theirs}"}
        )

        assert response.json()["items"] == []

    async def test_another_student_cannot_move_it(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mine, _ = await _student(session, email="mine2@example.test")
        theirs, _ = await _student(session, email="theirs2@example.test")
        job = await _job(session, source_job_id="s2")
        await session.commit()

        created = await client.post(
            "/api/v1/applications",
            json={"job_id": job.id},
            headers={"Authorization": f"Bearer {mine}"},
        )

        response = await client.patch(
            f"/api/v1/applications/{created.json()['id']}",
            json={"status": "rejected"},
            headers={"Authorization": f"Bearer {theirs}"},
        )

        # 404 rather than 403: a different code would confirm the id exists, which is what an
        # enumeration attempt is trying to learn.
        assert response.status_code == 404

    async def test_it_requires_signing_in(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        job = await _job(session, source_job_id="s3")
        await session.commit()

        assert (await client.get("/api/v1/applications")).status_code == 401
        assert (
            await client.post("/api/v1/applications", json={"job_id": job.id})
        ).status_code == 401


class TestAskingAboutOnePosting:
    """The posting page asks this on every visit, so the untracked answer must be ordinary."""

    async def test_an_untracked_posting_answers_null_rather_than_404(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token, _ = await _student(session)
        job = await _job(session, source_job_id="f1")
        await session.commit()

        response = await client.get(
            f"/api/v1/applications/for-job/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json() is None

    async def test_a_tracked_posting_returns_its_status(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token, _ = await _student(session)
        job = await _job(session, source_job_id="f2")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.post(
            "/api/v1/applications",
            json={"job_id": job.id, "status": "interviewing"},
            headers=headers,
        )

        response = await client.get(f"/api/v1/applications/for-job/{job.id}", headers=headers)

        assert response.json()["status"] == "interviewing"
        assert response.json()["job_id"] == job.id

    async def test_the_literal_path_wins_over_the_id_route(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """`/for-job/1` must not be read as application id "for-job" — the trap /parsed once hit."""
        token, _ = await _student(session)
        job = await _job(session, source_job_id="f3")
        await session.commit()

        response = await client.get(
            f"/api/v1/applications/for-job/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    async def test_it_does_not_leak_another_student_s_application(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mine, _ = await _student(session, email="f-mine@example.test")
        theirs, _ = await _student(session, email="f-theirs@example.test")
        job = await _job(session, source_job_id="f4")
        await session.commit()

        await client.post(
            "/api/v1/applications",
            json={"job_id": job.id, "status": "offer"},
            headers={"Authorization": f"Bearer {mine}"},
        )

        response = await client.get(
            f"/api/v1/applications/for-job/{job.id}",
            headers={"Authorization": f"Bearer {theirs}"},
        )

        assert response.json() is None


class TestRemovingOne:
    async def test_untracking_removes_the_row(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token, _ = await _student(session)
        job = await _job(session, source_job_id="d1")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        created = await client.post(
            "/api/v1/applications", json={"job_id": job.id}, headers=headers
        )
        deleted = await client.delete(
            f"/api/v1/applications/{created.json()['id']}", headers=headers
        )

        assert deleted.status_code == 204
        assert (await client.get("/api/v1/applications", headers=headers)).json()["items"] == []

    async def test_withdrawing_keeps_the_history(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Distinct from deleting, which would lose the resume and the draft attached to it."""
        token, _ = await _student(session)
        job = await _job(session, source_job_id="d2")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        created = await client.post(
            "/api/v1/applications",
            json={"job_id": job.id, "status": "applied"},
            headers=headers,
        )
        withdrawn = await client.patch(
            f"/api/v1/applications/{created.json()['id']}",
            json={"status": "withdrawn"},
            headers=headers,
        )

        assert withdrawn.json()["status"] == "withdrawn"
        assert withdrawn.json()["applied_at"] is not None, "it still happened"
        assert len((await client.get("/api/v1/applications", headers=headers)).json()["items"]) == 1
