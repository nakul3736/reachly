from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OutreachDraftRow(Base):
    """One introduction email, for one posting, written from one upload of the resume.

    Stored for the same reason a tailored resume is: the student needs to see what they sent. An email
    they cannot re-read is one they cannot follow up on, and regenerating would spend a model call to
    answer a question already answered, with different words, since generation is not deterministic.

    Keyed on the upload as well as the posting, so a re-uploaded resume produces a fresh draft instead
    of an email describing work the student has since removed from their resume.

    Named with a `Row` suffix because `OutreachDraft` is already the domain object this stores. Two
    identical names in one codebase - one a dataclass, one a table - is a confusion that costs an hour
    the first time somebody imports the wrong one.
    """

    __tablename__ = "outreach_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)

    # Nullable because a student with no resume still gets the assembled draft, and refusing to store
    # it would mean regenerating on every visit for exactly the people who have the least to show.
    resume_master_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_masters.id", ondelete="CASCADE"), index=True, nullable=True
    )

    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)

    # Why the message says what it says, as shown to the student.
    evidence: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # True when a model wrote it from the resume and the posting and the result passed validation.
    # False when this is the assembled fallback. Stored rather than inferred because the two are
    # indistinguishable from the text alone, and the interface must not present a template as writing.
    written: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id", "job_id", "resume_master_id", name="uq_outreach_student_job_resume"
        ),
    )
