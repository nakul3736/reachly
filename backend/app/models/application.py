from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApplicationStatus(StrEnum):
    """Where one application stands, in the student's own words.

    Every value is a fact the student reports, not one Reachly infers. It cannot know: it does not
    submit the form and it does not send the email (ADR 0004), so it has no view of the outcome. A
    tracker that guessed would be wrong in the direction that hurts - marking something applied because
    a link was clicked, when the student read the form and closed it.

    `saved` exists so the list is useful before anything has been sent, which is when a graduate most
    needs somewhere to put the twelve postings they are still deciding between.

    `withdrawn` is here because the alternative is deleting the row, and deleting loses the tailored
    resume and the draft attached to it. A student who walked away from a process still wants the
    sentences they wrote for it.
    """

    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Application(Base):
    """One posting a student is pursuing, and what has happened to it.

    The row is deliberately thin. It records status, when the student said each thing happened, and a
    pointer to the tailored resume they actually sent — that pointer is the reason this table is worth
    having rather than a bookmark list. Two months later, an interview invitation arrives and the
    question is "what did I claim?", which is unanswerable without knowing which version went out.
    """

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)

    status: Mapped[str] = mapped_column(String(16), default=ApplicationStatus.SAVED, index=True)

    # Which tailored resume was sent. Nullable: a student may apply with their master resume, and
    # pretending otherwise would put a false answer in the one field this table exists to answer.
    #
    # SET NULL rather than CASCADE on delete. Losing the record of the resume must never silently
    # delete the record of the application — the application happened either way, and a row vanishing
    # from a tracker is a bug the student discovers as a missing interview.
    tailored_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("tailored_resumes.id", ondelete="SET NULL"), nullable=True
    )

    # The student's own notes: who they spoke to, what was asked, what to follow up on.
    notes: Mapped[str] = mapped_column(Text, default="")

    # When the student said they applied, which is not when the row was created — `saved` comes first
    # for most postings, sometimes weeks first, and a pipeline that cannot tell the two apart cannot
    # answer "how long has this been outstanding?".
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # One row per posting per student. A second application to the same posting is not a new
        # application, it is a mistake, and the constraint turns it into a visible error rather than
        # two rows in a tracker that disagree about the status.
        UniqueConstraint("student_id", "job_id", name="uq_application_student_job"),
    )
