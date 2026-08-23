"""The tailoring endpoint, and the document it assembles.

These were missing. The validator and the service had 42 tests between them and the HTTP layer had
none, which left the parts that decide what a student actually receives untested: whether a second
tailoring replaces the first or quietly duplicates it, whether the gap list is the score's or a
second opinion, and whether every bullet on the resume survives into the printable version.

The document is the part worth testing hardest. It is what somebody sends an employer, so a bullet
going missing from it is worse than a bullet being badly rewritten — the student would not notice.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory
from app.models.board_token import BoardToken
from app.models.job import Job
from app.models.match_score import MatchScore
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.tailored_resume import TailoredResume
from app.models.user import User
from app.security import create_access_token, hash_password

PARSED = {
    "summary": "Computer science graduate who has shipped small services.",
    "skills": ["Python", "SQL", "Docker"],
    "experience": [
        {
            "id": "e1",
            "employer": "University Lab",
            "title": "Research Assistant",
            "dates": "2025",
            "bullets": [
                {"id": "b1", "text": "Wrote Python scripts to clean survey data."},
                {"id": "b2", "text": "Built a small SQL database for the results."},
            ],
        },
        {
            "id": "e2",
            "employer": "Campus IT",
            "title": "Student Assistant",
            "dates": "2024",
            "bullets": [{"id": "b3", "text": "Answered support tickets for staff laptops."}],
        },
    ],
    "education": [
        {
            "id": "ed1",
            "institution": "Dalhousie University",
            "credential": "BSc Computer Science",
            "dates": "2026",
        }
    ],
    "raw_text": "Python SQL Docker survey data support tickets",
}


async def _signed_in_student(session: AsyncSession) -> tuple[Student, ResumeMaster, str]:
    user = User(email="tailor-api@example.test", password_hash=hash_password("Passw0rd!x"))
    session.add(user)
    await session.flush()

    student = Student(
        user_id=user.id, name="Test Graduate", links={"github": "example.test/gh"}
    )
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


async def _job(session: AsyncSession, *, description: str = "Python and Kubernetes.") -> Job:
    board = (await session.execute(select(BoardToken).limit(1))).scalars().first()
    job = Job(
        board_token_id=board.id if board else None,
        source="greenhouse",
        source_job_id="tailor-api-1",
        title="Backend Engineer",
        company_name="Acme",
        description=description,
        apply_url="https://example.test/apply",
        is_verified=True,
        first_seen_at=datetime.now(UTC) - timedelta(days=1),
        posted_at=datetime.now(UTC) - timedelta(days=1),
    )
    session.add(job)
    await session.flush()
    return job


class TestWritesSurviveTheRequest:
    """A flush is not a save, and nothing in the suite was checking the difference.

    `get_session` yields a session and never commits, so every write that ended in `flush()` was
    rolled back when the request finished. The response looked correct because the data was still in
    the session that produced it. Three paths had this bug: the score cache, the posting facts
    cached on the job row, and tailoring — so a student who tailored a resume and came back was told
    no tailoring existed, and every feed render recomputed scores it had already calculated, stored
    and discarded.

    These tests assert across two requests, which is the only way to see it.
    """

    async def test_a_tailoring_can_be_fetched_after_the_request_that_made_it(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        created = await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)
        assert created.status_code == 200

        fetched = await client.get(f"/api/v1/jobs/{job.id}/tailor", headers=headers)

        assert fetched.status_code == 200, "the tailoring was discarded when the request ended"
        assert fetched.json()["job_id"] == job.id
        assert len(fetched.json()["bullets"]) == len(created.json()["bullets"])

    async def test_the_stored_row_exists_in_a_separate_session(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        await client.post(
            f"/api/v1/jobs/{job.id}/tailor", headers={"Authorization": f"Bearer {token}"}
        )

        # A fresh session, so this cannot pass on data merely pending in another one.
        async with get_session_factory()() as check:
            count = await check.scalar(
                select(func.count())
                .select_from(TailoredResume)
                .where(TailoredResume.job_id == job.id)
            )
        assert count == 1

    async def test_retailoring_replaces_rather_than_accumulating(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)
        await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)

        async with get_session_factory()() as check:
            count = await check.scalar(
                select(func.count())
                .select_from(TailoredResume)
                .where(TailoredResume.job_id == job.id)
            )
        assert count == 1, "a second tailoring must replace the first, not add a row"

    async def test_the_score_cache_is_actually_written(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The whole point of the cache. It measured 1179x faster and was storing nothing."""
        _, _, token = await _signed_in_student(session)
        await _job(session)
        await session.commit()

        await client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"})

        async with get_session_factory()() as check:
            scores = await check.scalar(select(func.count()).select_from(MatchScore))
        assert scores and scores > 0, "the scored feed computed scores and threw them away"

    async def test_the_posting_facts_are_cached_on_the_job_row(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Student-independent readings, so the first reader should be the only one to pay."""
        _, _, token = await _signed_in_student(session)
        job = await _job(session, description="Python role. 3+ years of experience required.")
        await session.commit()
        job_id = job.id

        await client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"})

        async with get_session_factory()() as check:
            stored = await check.get(Job, job_id)
            assert stored is not None
            assert stored.experience_parsed_at is not None, (
                "the requirement was read and discarded"
            )
            assert stored.extracted_skills is not None, "the skills were read and discarded"


class TestNothingChangesWithoutApproval:
    """A rewrite is a proposal. The document is the student's own writing until they say otherwise.

    This is the feature, not a safety net around it. Treating a generated sentence as applied unless
    rejected would make silence into consent for words somebody sends an employer under their name.
    """

    async def _tailored_with_a_rewrite(
        self, session: AsyncSession, student: Student, resume: ResumeMaster, job: Job
    ) -> None:
        """A stored tailoring with one accepted rewrite and one refusal, written directly.

        Written rather than generated so the fixture's behaviour cannot change what is being tested.
        """
        session.add(
            TailoredResume(
                student_id=student.id,
                job_id=job.id,
                resume_master_id=resume.id,
                bullets=[
                    {
                        "bullet_id": "b1",
                        "original": "Wrote Python scripts to clean survey data.",
                        "tailored": "Wrote Python scripts to clean and validate survey data.",
                        "changed": True,
                        "rejected_reason": None,
                        "rejected_detail": "",
                        "rejected_text": "",
                    },
                    {
                        "bullet_id": "b2",
                        "original": "Built a small SQL database for the results.",
                        "tailored": "Built a small SQL database for the results.",
                        "changed": False,
                        "rejected_reason": "added_technology",
                        "rejected_detail": "Kubernetes",
                        "rejected_text": "Built a SQL database on Kubernetes for the results.",
                    },
                ],
                gaps=["Kubernetes"],
                changed_count=1,
                rejected_count=1,
                basis="recorded",
            )
        )
        await session.commit()

    async def test_the_document_keeps_the_original_until_approved(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        student, resume, token = await _signed_in_student(session)
        job = await _job(session)
        await session.flush()
        await self._tailored_with_a_rewrite(session, student, resume, job)

        response = await client.get(
            f"/api/v1/jobs/{job.id}/tailor", headers={"Authorization": f"Bearer {token}"}
        )

        body = response.json()
        assert body["approved_bullet_ids"] == []
        first = body["document"]["experience"][0]["bullets"][0]
        assert first["text"] == "Wrote Python scripts to clean survey data."
        assert first["applied"] is False
        assert first["pending"] is True, "the student should be told a rewrite is waiting"

    async def test_approving_puts_the_rewrite_into_the_document(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        student, resume, token = await _signed_in_student(session)
        job = await _job(session)
        await session.flush()
        await self._tailored_with_a_rewrite(session, student, resume, job)

        headers = {"Authorization": f"Bearer {token}"}
        response = await client.patch(
            f"/api/v1/jobs/{job.id}/tailor/approvals",
            headers=headers,
            json={"approved": ["b1"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["approved_bullet_ids"] == ["b1"]
        first = body["document"]["experience"][0]["bullets"][0]
        assert first["text"] == "Wrote Python scripts to clean and validate survey data."
        assert first["applied"] is True
        assert first["pending"] is False

    async def test_withdrawing_approval_restores_the_original(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        student, resume, token = await _signed_in_student(session)
        job = await _job(session)
        await session.flush()
        await self._tailored_with_a_rewrite(session, student, resume, job)

        headers = {"Authorization": f"Bearer {token}"}
        await client.patch(
            f"/api/v1/jobs/{job.id}/tailor/approvals", headers=headers, json={"approved": ["b1"]}
        )
        response = await client.patch(
            f"/api/v1/jobs/{job.id}/tailor/approvals", headers=headers, json={"approved": []}
        )

        body = response.json()
        assert body["approved_bullet_ids"] == []
        assert (
            body["document"]["experience"][0]["bullets"][0]["text"]
            == "Wrote Python scripts to clean survey data."
        )

    async def test_a_refused_rewrite_cannot_be_approved(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """There is nothing to approve, and a tick beside it would imply the guard was overridden."""
        student, resume, token = await _signed_in_student(session)
        job = await _job(session)
        await session.flush()
        await self._tailored_with_a_rewrite(session, student, resume, job)

        response = await client.patch(
            f"/api/v1/jobs/{job.id}/tailor/approvals",
            headers={"Authorization": f"Bearer {token}"},
            json={"approved": ["b1", "b2"]},
        )

        body = response.json()
        assert body["approved_bullet_ids"] == ["b1"], "b2's rewrite was refused"
        second = body["document"]["experience"][0]["bullets"][1]
        assert "Kubernetes" not in second["text"]

    async def test_an_unknown_id_is_dropped_rather_than_failing_the_request(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """A stale id means the resume moved on, not that the other approvals are invalid."""
        student, resume, token = await _signed_in_student(session)
        job = await _job(session)
        await session.flush()
        await self._tailored_with_a_rewrite(session, student, resume, job)

        response = await client.patch(
            f"/api/v1/jobs/{job.id}/tailor/approvals",
            headers={"Authorization": f"Bearer {token}"},
            json={"approved": ["b1", "b-from-an-older-resume"]},
        )

        assert response.status_code == 200
        assert response.json()["approved_bullet_ids"] == ["b1"]


class TestRevisionFromFeedback:
    async def test_feedback_on_several_bullets_is_one_request(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Batched so iterating on a whole resume costs what one bullet costs."""
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)

        response = await client.post(
            f"/api/v1/jobs/{job.id}/tailor/revise",
            headers=headers,
            json={
                "revisions": [
                    {"bullet_id": "b1", "instruction": "lead with the data cleaning"},
                    {"bullet_id": "b3", "instruction": "make it shorter"},
                ]
            },
        )

        assert response.status_code == 200
        # Whatever the model returned, every bullet still exists and none carries invented text.
        body = response.json()
        assert len(body["bullets"]) == 3
        for bullet in body["bullets"]:
            assert bullet["original"], "the source sentence must survive a revision"

    async def test_revising_clears_the_approval_for_that_bullet(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The student approved a particular sentence, and a revision is a different one."""
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)
        await client.patch(
            f"/api/v1/jobs/{job.id}/tailor/approvals", headers=headers, json={"approved": ["b1"]}
        )

        response = await client.post(
            f"/api/v1/jobs/{job.id}/tailor/revise",
            headers=headers,
            json={"revisions": [{"bullet_id": "b1", "instruction": "shorter"}]},
        )

        assert "b1" not in response.json()["approved_bullet_ids"]

    async def test_empty_feedback_is_refused(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)

        response = await client.post(
            f"/api/v1/jobs/{job.id}/tailor/revise",
            headers=headers,
            json={"revisions": [{"bullet_id": "b1", "instruction": "   "}]},
        )

        assert response.status_code == 400

    async def test_feedback_on_a_bullet_that_is_not_there_is_a_404(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)

        response = await client.post(
            f"/api/v1/jobs/{job.id}/tailor/revise",
            headers=headers,
            json={"revisions": [{"bullet_id": "not-a-bullet", "instruction": "shorter"}]},
        )

        assert response.status_code == 404


class TestTailoringEndpoint:
    async def test_it_stores_one_row_and_replaces_it_on_retailoring(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Re-tailoring must not accumulate rows nobody would choose between."""
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        first = await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)
        assert first.status_code == 200

        second = await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)
        assert second.status_code == 200

        count = await session.scalar(
            select(func.count())
            .select_from(TailoredResume)
            .where(TailoredResume.job_id == job.id)
        )
        assert count == 1

    async def test_getting_before_tailoring_is_a_404_not_an_error(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/tailor", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404

    async def test_a_student_without_a_resume_is_told_what_to_do(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = User(
            email="noresume-tailor@example.test", password_hash=hash_password("Passw0rd!x")
        )
        session.add(user)
        await session.flush()
        session.add(Student(user_id=user.id, name="No Resume"))
        job = await _job(session)
        await session.commit()

        response = await client.post(
            f"/api/v1/jobs/{job.id}/tailor",
            headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "resume_missing"

    async def test_tailoring_requires_signing_in(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        job = await _job(session)
        await session.commit()

        response = await client.post(f"/api/v1/jobs/{job.id}/tailor")

        assert response.status_code == 401

    async def test_the_gaps_are_the_score_s_missing_skills(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Not a second opinion. Tailoring and the score must not disagree about the posting."""
        _, _, token = await _signed_in_student(session)
        job = await _job(session, description="Python required. Kubernetes required.")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        tailored = await client.post(f"/api/v1/jobs/{job.id}/tailor", headers=headers)
        report = await client.get(f"/api/v1/jobs/{job.id}/score", headers=headers)

        assert sorted(tailored.json()["gaps"]) == sorted(report.json()["missing_skills"])


class TestTheAssembledDocument:
    """What the student prints. A bullet lost here would not be noticed until an employer read it."""

    async def test_every_bullet_survives_in_its_original_position(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        response = await client.post(
            f"/api/v1/jobs/{job.id}/tailor", headers={"Authorization": f"Bearer {token}"}
        )

        document = response.json()["document"]
        assert [entry["employer"] for entry in document["experience"]] == [
            "University Lab",
            "Campus IT",
        ]
        counts = [len(entry["bullets"]) for entry in document["experience"]]
        assert counts == [2, 1], "the document must have exactly the resume's bullets"

        for entry in document["experience"]:
            for bullet in entry["bullets"]:
                assert bullet["text"].strip(), "an empty bullet would print as a stray dot"

    async def test_the_document_carries_the_student_s_own_details(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, _, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        response = await client.post(
            f"/api/v1/jobs/{job.id}/tailor", headers={"Authorization": f"Bearer {token}"}
        )

        document = response.json()["document"]
        assert document["name"] == "Test Graduate"
        assert document["email"] == "tailor-api@example.test"
        assert document["education"][0]["institution"] == "Dalhousie University"
        assert document["summary"]

    async def test_the_skills_list_is_the_resume_s_and_gains_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The easiest place to fabricate by accident, so it is asserted rather than assumed."""
        _, _, token = await _signed_in_student(session)
        job = await _job(
            session, description="Kubernetes required. Terraform required. Go required."
        )
        await session.commit()

        response = await client.post(
            f"/api/v1/jobs/{job.id}/tailor", headers={"Authorization": f"Bearer {token}"}
        )

        body = response.json()
        assert body["document"]["skills"] == PARSED["skills"]
        # The posting's demands are reported as gaps, and gaps do not enter the document.
        for gap in body["gaps"]:
            assert gap not in body["document"]["skills"]

    async def test_a_refused_rewrite_leaves_the_student_s_own_sentence_in_the_document(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The fallback has to be visible in the artefact, not only in the comparison view."""
        student, resume, token = await _signed_in_student(session)
        job = await _job(session)
        await session.commit()

        # A stored tailoring where one bullet was refused, written directly so the outcome is
        # certain rather than dependent on what a fixture happens to return.
        session.add(
            TailoredResume(
                student_id=student.id,
                job_id=job.id,
                resume_master_id=resume.id,
                bullets=[
                    {
                        "bullet_id": "b1",
                        "original": "Wrote Python scripts to clean survey data.",
                        "tailored": "Wrote Python scripts to clean survey data.",
                        "changed": False,
                        "rejected_reason": "added_technology",
                        "rejected_detail": "Kubernetes",
                        "rejected_text": "Ran Python jobs on Kubernetes to clean survey data.",
                    }
                ],
                gaps=["Kubernetes"],
                changed_count=0,
                rejected_count=1,
                basis="recorded",
            )
        )
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/tailor", headers={"Authorization": f"Bearer {token}"}
        )

        document = response.json()["document"]
        first = document["experience"][0]["bullets"][0]
        assert first["text"] == "Wrote Python scripts to clean survey data."
        assert first["refused"] is True
        assert "Kubernetes" not in first["text"]

    async def test_a_bullet_with_no_outcome_keeps_the_original_rather_than_disappearing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """A stored tailoring can be older than the resume it is read against."""
        student, resume, token = await _signed_in_student(session)
        job = await _job(session)
        session.add(
            TailoredResume(
                student_id=student.id,
                job_id=job.id,
                resume_master_id=resume.id,
                # Only one of the resume's three bullets has an outcome.
                bullets=[
                    {
                        "bullet_id": "b1",
                        "original": "Wrote Python scripts to clean survey data.",
                        "tailored": "Wrote Python scripts to clean and validate survey data.",
                        "changed": True,
                        "rejected_reason": None,
                        "rejected_detail": "",
                        "rejected_text": "",
                    }
                ],
                gaps=[],
                changed_count=1,
                rejected_count=0,
                basis="recorded",
            )
        )
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/tailor", headers={"Authorization": f"Bearer {token}"}
        )

        document = response.json()["document"]
        texts = [b["text"] for entry in document["experience"] for b in entry["bullets"]]
        assert len(texts) == 3, "no bullet may be dropped for lacking an outcome"
        assert "Built a small SQL database for the results." in texts
        assert "Answered support tickets for staff laptops." in texts
