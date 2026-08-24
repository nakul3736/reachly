"""Approvals across a resume re-upload.

The behaviour being fixed: a student ticks eight suggestions, fixes one typo in their master resume,
re-uploads, and every tick is gone — because tailorings are keyed on the upload and the new one starts
empty. The cost is real and the purpose was nil, since most bullets in the new upload are the same
sentences they already read.

The danger in fixing it is worse than the annoyance, which is why the rule is character-identical text
rather than a matching bullet id. Ids are derived from the *original* sentence, so a surviving id proves
only that the student did not edit that line — the rewrite is regenerated, generation is not
deterministic, and the same id can come back carrying a different proposal. Approving text nobody read
is precisely what the approval mechanism exists to prevent, and it would fail silently: the document
would simply contain a sentence the student never saw.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tailoring import _carry_approvals
from app.models.board_token import BoardToken
from app.models.job import Job
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.tailored_resume import TailoredResume
from app.models.user import User
from app.security import hash_password

PARSED = {
    "summary": "Graduate",
    "skills": ["Python"],
    "experience": [],
    "projects": [],
    "education": [],
    "raw_text": "Python",
}


async def _setup(session: AsyncSession) -> tuple[int, int, int, int]:
    """A student with two resume uploads and one posting."""
    user = User(email="carry@example.test", password_hash=hash_password("Passw0rd!x"))
    session.add(user)
    await session.flush()
    student = Student(user_id=user.id, name="Test Graduate")
    session.add(student)
    await session.flush()

    old = ResumeMaster(
        student_id=student.id,
        version=1,
        filename="v1.pdf",
        byte_size=8,
        pdf_bytes=b"%PDF-1.4",
        parsed_json=PARSED,
        is_active=False,
    )
    new = ResumeMaster(
        student_id=student.id,
        version=2,
        filename="v2.pdf",
        byte_size=8,
        pdf_bytes=b"%PDF-1.4",
        parsed_json=PARSED,
        is_active=True,
    )
    session.add_all([old, new])
    await session.flush()

    board = (await session.execute(select(BoardToken).limit(1))).scalars().first()
    job = Job(
        board_token_id=board.id if board else None,
        source="greenhouse",
        source_job_id="carry-1",
        title="Backend Engineer",
        company_name="Acme",
        description="Python required.",
        apply_url="https://example.test/apply",
        is_verified=True,
        first_seen_at=datetime.now(UTC) - timedelta(days=1),
        posted_at=datetime.now(UTC) - timedelta(days=1),
    )
    session.add(job)
    await session.flush()

    return student.id, job.id, old.id, new.id


def _bullet(
    bullet_id: str,
    tailored: str,
    *,
    changed: bool = True,
    rejected: str | None = None,
) -> dict[str, object]:
    return {
        "bullet_id": bullet_id,
        "original": "Built a thing.",
        "tailored": tailored,
        "changed": changed,
        "rejected_reason": rejected,
        "rejected_detail": "",
        "rejected_text": "",
        "unavailable": False,
    }


async def _previous(
    session: AsyncSession,
    *,
    student_id: int,
    job_id: int,
    resume_id: int,
    bullets: list[dict[str, object]],
    approved: list[str],
) -> TailoredResume:
    row = TailoredResume(
        student_id=student_id,
        job_id=job_id,
        resume_master_id=resume_id,
        bullets=bullets,
        gaps=[],
        changed_count=sum(1 for b in bullets if b.get("changed")),
        rejected_count=0,
        approved_bullet_ids=approved,
    )
    session.add(row)
    await session.flush()
    return row


class TestCarryingApprovalsForward:
    async def test_an_identical_rewrite_keeps_its_tick(self, session: AsyncSession) -> None:
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("b1", "Built a Python pipeline for survey data.")],
            approved=["b1"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[_bullet("b1", "Built a Python pipeline for survey data.")],
        )

        assert carried == ["b1"], "the student has already read this exact sentence"

    async def test_a_changed_rewrite_loses_its_tick(self, session: AsyncSession) -> None:
        """Generation is not deterministic, so the same id can return different text."""
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("b1", "Built a Python pipeline for survey data.")],
            approved=["b1"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[_bullet("b1", "Built a Python pipeline processing survey data at scale.")],
        )

        assert carried == []

    async def test_a_single_character_difference_loses_its_tick(
        self, session: AsyncSession
    ) -> None:
        """This is the exact string that gets printed and sent, so "close enough" is not a standard."""
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("b1", "Built a Python pipeline for survey data.")],
            approved=["b1"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[_bullet("b1", "Built a Python pipeline for survey data")],
        )

        assert carried == []

    async def test_trailing_whitespace_is_not_forgiven(self, session: AsyncSession) -> None:
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("b1", "Built a Python pipeline.")],
            approved=["b1"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[_bullet("b1", "Built a Python pipeline. ")],
        )

        assert carried == []

    async def test_an_unapproved_bullet_stays_unapproved(self, session: AsyncSession) -> None:
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[
                _bullet("b1", "Ticked sentence."),
                _bullet("b2", "Never ticked sentence."),
            ],
            approved=["b1"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[
                _bullet("b1", "Ticked sentence."),
                _bullet("b2", "Never ticked sentence."),
            ],
        )

        assert carried == ["b1"]

    async def test_a_now_refused_rewrite_cannot_arrive_approved(
        self, session: AsyncSession
    ) -> None:
        """The invariant holds through this path too: a refusal is never approvable."""
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("b1", "Built a Python pipeline.")],
            approved=["b1"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[
                _bullet(
                    "b1",
                    "Built a Python pipeline.",
                    changed=False,
                    rejected="added_technology",
                )
            ],
        )

        assert carried == []

    async def test_an_unchanged_bullet_is_not_an_approval(self, session: AsyncSession) -> None:
        """There is no suggestion to approve when nothing was proposed."""
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("b1", "Built a thing.")],
            approved=["b1"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[_bullet("b1", "Built a thing.", changed=False)],
        )

        assert carried == []

    async def test_a_deleted_bullet_carries_nothing(self, session: AsyncSession) -> None:
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("gone", "A sentence the student has since removed.")],
            approved=["gone"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[_bullet("b1", "A different sentence entirely.")],
        )

        assert carried == []

    async def test_nothing_is_carried_when_nothing_was_approved(
        self, session: AsyncSession
    ) -> None:
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("b1", "Built a Python pipeline.")],
            approved=[],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[_bullet("b1", "Built a Python pipeline.")],
        )

        assert carried == []

    async def test_a_first_ever_tailoring_carries_nothing(self, session: AsyncSession) -> None:
        student_id, job_id, _old_id, new_id = await _setup(session)

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id,
            current_resume_id=new_id,
            payload=[_bullet("b1", "Built a Python pipeline.")],
        )

        assert carried == []

    async def test_approvals_do_not_cross_between_postings(self, session: AsyncSession) -> None:
        """The same bullet tailored for two jobs produces two different sentences."""
        student_id, job_id, old_id, new_id = await _setup(session)
        await _previous(
            session,
            student_id=student_id,
            job_id=job_id,
            resume_id=old_id,
            bullets=[_bullet("b1", "Built a Python pipeline.")],
            approved=["b1"],
        )

        carried = await _carry_approvals(
            session,
            student_id=student_id,
            job_id=job_id + 999,
            current_resume_id=new_id,
            payload=[_bullet("b1", "Built a Python pipeline.")],
        )

        assert carried == []
