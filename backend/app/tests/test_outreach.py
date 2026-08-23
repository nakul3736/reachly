"""The outreach draft, which goes out under the student's name.

Two things are tested harder than the wording: that nothing specific in the message is unevidenced,
and that a missing input shortens the message rather than making it vaguer. A cold email is where a
writing tool is most tempted to invent enthusiasm, and a graduate who tells a company they have long
admired its work in distributed systems — having met it ninety seconds ago — is worse off than one who
sends four plain sentences that are true.

ADR 0004 is asserted too: Reachly produces a draft and never a send.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory
from app.domain.outreach import build_outreach_draft
from app.models.board_token import BoardToken
from app.models.job import Job
from app.models.outreach_draft import OutreachDraftRow
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.user import User
from app.security import create_access_token, hash_password


class TestTheDraftClaimsOnlyWhatIsGiven:
    def test_it_names_the_role_and_the_company(self) -> None:
        draft = build_outreach_draft(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            matched_skills=["Python", "PostgreSQL"],
        )

        assert "Backend Engineer" in draft.subject
        assert "Nakul Patel" in draft.subject
        assert "Acme" in draft.body
        assert draft.body.strip().endswith("Nakul Patel"), "it is signed by the sender"

    def test_it_names_only_the_skills_it_was_given(self) -> None:
        draft = build_outreach_draft(
            student_name="A Student",
            job_title="Backend Engineer",
            company="Acme",
            matched_skills=["Python", "SQL"],
        )

        assert "Python" in draft.body
        assert "SQL" in draft.body
        for invented in ("Kubernetes", "Terraform", "AWS", "Go"):
            assert invented not in draft.body

    def test_it_caps_the_skills_so_it_does_not_read_as_a_keyword_dump(self) -> None:
        draft = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Acme",
            matched_skills=["Python", "SQL", "Docker", "React", "Java", "Rust"],
        )

        named = sum(
            1
            for skill in ("Python", "SQL", "Docker", "React", "Java", "Rust")
            if skill in draft.body
        )
        assert named == 3

    def test_with_no_matched_skills_it_gets_shorter_not_vaguer(self) -> None:
        """The failure to avoid: replacing missing evidence with claimed enthusiasm."""
        with_skills = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Acme",
            matched_skills=["Python"],
        )
        without = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Acme",
            matched_skills=[],
        )

        assert len(without.body) < len(with_skills.body)
        for flattery in ("passionate", "admire", "excited", "dream", "perfect fit", "love"):
            assert flattery not in without.body.lower()

    def test_the_company_hook_is_only_used_when_there_is_something_to_say(self) -> None:
        silent = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Acme",
            matched_skills=[],
            other_open_roles=0,
        )
        assert "other role" not in silent.body

        speaking = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Acme",
            matched_skills=[],
            other_open_roles=4,
        )
        assert "4 other roles" in speaking.body

    def test_one_other_role_reads_as_singular(self) -> None:
        draft = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Acme",
            matched_skills=[],
            other_open_roles=1,
        )

        assert "1 other role open" in draft.body
        assert "roles" not in draft.body

    def test_a_very_large_count_is_left_out(self) -> None:
        """From the real index: an Airbnb posting produced "209 other roles open at the moment".

        True, useless, and it reads as scraped rather than noticed. At four openings the remark is a
        genuine observation about a company and an honest invitation to be redirected; at two hundred
        it tells a recruiter something they know better than anyone and makes the sender look
        automated.
        """
        draft = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Airbnb",
            matched_skills=["React"],
            other_open_roles=209,
        )

        assert "209" not in draft.body
        assert "other role" not in draft.body
        # And the claim disappears from the evidence with it, rather than explaining an absent line.
        assert not any("209" in line for line in draft.evidence)
        # The rest of the message still stands on its own.
        assert "React" in draft.body
        assert "Airbnb" in draft.body

    def test_a_count_at_the_boundary_is_still_worth_saying(self) -> None:
        draft = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Acme",
            matched_skills=[],
            other_open_roles=12,
        )

        assert "12 other roles" in draft.body

    def test_every_specific_claim_has_a_line_of_evidence(self) -> None:
        draft = build_outreach_draft(
            student_name="A Student",
            job_title="Engineer",
            company="Acme",
            matched_skills=["Python"],
            other_open_roles=3,
        )

        # Role and company, the skills, and the company hook: three claims, three explanations.
        assert len(draft.evidence) == 3
        assert any("posting" in line for line in draft.evidence)
        assert any("match score" in line for line in draft.evidence)
        assert any("whole job boards" in line for line in draft.evidence)

    def test_it_is_the_same_draft_every_time(self) -> None:
        """Deterministic, because it is assembled rather than generated."""
        args = {
            "student_name": "A Student",
            "job_title": "Engineer",
            "company": "Acme",
            "matched_skills": ["Python", "SQL"],
            "other_open_roles": 2,
        }

        assert build_outreach_draft(**args) == build_outreach_draft(**args)  # type: ignore[arg-type]

    def test_a_student_with_no_name_still_gets_a_usable_draft(self) -> None:
        draft = build_outreach_draft(
            student_name="  ",
            job_title="Engineer",
            company="Acme",
            matched_skills=[],
        )

        assert draft.subject
        assert draft.body


PARSED = {
    "summary": "Graduate developer",
    "skills": ["Python", "SQL", "Docker"],
    "experience": [
        {"id": "e1", "employer": "Lab", "title": "Intern", "dates": "2025", "bullets": []}
    ],
    "education": [],
    "raw_text": "Python SQL Docker",
}


async def _student(session: AsyncSession, *, with_resume: bool = True) -> str:
    user = User(email="outreach@example.test", password_hash=hash_password("Passw0rd!x"))
    session.add(user)
    await session.flush()
    student = Student(user_id=user.id, name="Test Graduate")
    session.add(student)
    await session.flush()
    if with_resume:
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


async def _job(session: AsyncSession, *, company: str, source_job_id: str) -> Job:
    board = (await session.execute(select(BoardToken).limit(1))).scalars().first()
    job = Job(
        board_token_id=board.id if board else None,
        source="greenhouse",
        source_job_id=source_job_id,
        title="Backend Engineer",
        company_name=company,
        description="Python and SQL required. Kubernetes required.",
        apply_url="https://example.test/apply",
        is_verified=True,
        first_seen_at=datetime.now(UTC) - timedelta(days=1),
        posted_at=datetime.now(UTC) - timedelta(days=1),
    )
    session.add(job)
    await session.flush()
    return job


class TestTheOutreachEndpoint:
    async def test_it_returns_a_draft_and_never_sends(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """ADR 0004. The response is text and an apply link; there is no send endpoint to call."""
        token = await _student(session)
        job = await _job(session, company="Acme", source_job_id="o1")
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/outreach", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["subject"] and body["body"]
        assert body["apply_url"] == "https://example.test/apply"
        assert "send" not in {route.lower() for route in body}

    async def test_the_named_skills_come_from_the_score(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """So the email cannot claim a skill the score does not credit."""
        token = await _student(session)
        job = await _job(session, company="Acme", source_job_id="o2")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        outreach = await client.get(f"/api/v1/jobs/{job.id}/outreach", headers=headers)
        report = await client.get(f"/api/v1/jobs/{job.id}/score", headers=headers)

        matched = report.json()["matched_skills"]
        missing = report.json()["missing_skills"]
        drafted = outreach.json()["body"]

        assert any(skill in drafted for skill in matched), (
            "it should name what the resume evidences"
        )
        for gap in missing:
            assert gap not in drafted, f"the draft must not claim {gap}, which the resume lacks"

    async def test_it_counts_the_company_s_other_open_roles(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token = await _student(session)
        job = await _job(session, company="Acme", source_job_id="o3")
        await _job(session, company="Acme", source_job_id="o4")
        await _job(session, company="Acme", source_job_id="o5")
        await _job(session, company="Other Co", source_job_id="o6")
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/outreach", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.json()["other_open_roles"] == 2, "same company, excluding this posting"

    async def test_a_closed_posting_is_not_counted_as_an_opening(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token = await _student(session)
        job = await _job(session, company="Acme", source_job_id="o7")
        closed = await _job(session, company="Acme", source_job_id="o8")
        closed.closed_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/outreach", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.json()["other_open_roles"] == 0

    async def test_a_student_without_a_resume_still_gets_a_draft(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Shorter, with no skills sentence, rather than an error or an invented one."""
        token = await _student(session, with_resume=False)
        job = await _job(session, company="Acme", source_job_id="o9")
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/outreach", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["body"]

    async def test_it_requires_signing_in(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        job = await _job(session, company="Acme", source_job_id="o10")
        await session.commit()

        response = await client.get(f"/api/v1/jobs/{job.id}/outreach")

        assert response.status_code == 401

    async def test_the_draft_is_stored_so_a_second_visit_costs_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Queried through a separate session, because in this codebase a flush is not a save."""
        token = await _student(session)
        job = await _job(session, company="Acme", source_job_id="o11")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        first = await client.get(f"/api/v1/jobs/{job.id}/outreach", headers=headers)
        second = await client.get(f"/api/v1/jobs/{job.id}/outreach", headers=headers)

        assert first.status_code == 200
        assert second.json()["body"] == first.json()["body"]

        async with get_session_factory()() as other:
            stored = (
                (
                    await other.execute(
                        select(OutreachDraftRow).where(OutreachDraftRow.job_id == job.id)
                    )
                )
                .scalars()
                .all()
            )

        assert len(stored) == 1, "one row per posting per upload, not one per visit"
        assert stored[0].body == first.json()["body"]

    async def test_the_response_says_whether_it_was_written_or_assembled(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """A template presented as writing is a lie the student discovers by reading it."""
        token = await _student(session)
        job = await _job(session, company="Acme", source_job_id="o12")
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/outreach", headers={"Authorization": f"Bearer {token}"}
        )

        # Under DEMO_MODE there is no recorded reply for this prompt, so the fallback is expected —
        # and the flag must report that honestly rather than defaulting to the flattering answer.
        assert response.json()["written"] is False

    async def test_rewriting_replaces_the_stored_draft_rather_than_adding_one(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        token = await _student(session)
        job = await _job(session, company="Acme", source_job_id="o13")
        await session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        await client.get(f"/api/v1/jobs/{job.id}/outreach", headers=headers)
        again = await client.post(f"/api/v1/jobs/{job.id}/outreach/rewrite", headers=headers)

        assert again.status_code == 200

        async with get_session_factory()() as other:
            rows = (
                (
                    await other.execute(
                        select(OutreachDraftRow).where(OutreachDraftRow.job_id == job.id)
                    )
                )
                .scalars()
                .all()
            )

        assert len(rows) == 1

    async def test_rewriting_is_not_reachable_by_a_get(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """It spends a model call and replaces stored text, so a prefetch must not trigger it."""
        token = await _student(session)
        job = await _job(session, company="Acme", source_job_id="o14")
        await session.commit()

        response = await client.get(
            f"/api/v1/jobs/{job.id}/outreach/rewrite",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 405
