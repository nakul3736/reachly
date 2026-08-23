from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TailoredResume(Base):
    """One resume tailored to one posting, with the provenance of every bullet.

    Named for what it is rather than `ResumeVersion`, because `ResumeMaster` already means the
    uploaded document and two names one word apart would be read wrongly by whoever comes next.

    Stored rather than regenerated for two reasons. A student needs to see what they actually sent —
    an application they cannot review is one they cannot discuss in an interview. And regenerating
    would spend a model call to answer a question already answered, with a different result, since
    generation is not deterministic.
    """

    __tablename__ = "tailored_resumes"

    id: Mapped[int] = mapped_column(primary_key=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)

    # Which upload this was derived from. The same reasoning as MatchScore: including it means a
    # new upload does not invalidate anything, it simply stops matching, and this row stays true
    # about the resume it was built from.
    resume_master_id: Mapped[int] = mapped_column(
        ForeignKey("resume_masters.id", ondelete="CASCADE"), index=True
    )

    # The provenance map ADR 0006 requires: one entry per bullet, carrying the source bullet id,
    # the original text, what is shown, whether it changed, and the validator's verdict when a
    # rewrite was refused.
    #
    # The original is stored alongside rather than being looked up from the parse, deliberately.
    # The interface's central claim is "here is what changed", and a claim that depends on joining
    # against a document that may since have been replaced is a claim that can silently become
    # wrong.
    bullets: Mapped[list[dict[str, object]]] = mapped_column(JSONB)

    # Requirements the posting states that the resume does not support. The honest home for
    # everything tailoring is forbidden from inventing.
    gaps: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # How many bullets were rewritten and how many rewrites the validator refused. Kept as columns
    # rather than counted from the JSON so the interface can summarise without unpacking, and so
    # the refusal count is visible in the database when someone asks whether the guard ever fires.
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)

    # Which rewrites the student has personally approved, by bullet id.
    #
    # Empty is the meaningful default: a rewrite is a proposal, and until the student says otherwise
    # the document is their own writing. The alternative — treating a generated rewrite as applied
    # unless rejected — makes silence into consent for a sentence somebody is about to send an
    # employer under their own name, which is precisely the thing ADR 0006 exists to prevent.
    #
    # Stored as ids rather than a flag inside `bullets` so that re-tailoring, which replaces the
    # bullets payload wholesale, cannot quietly carry an old approval onto new text.
    approved_bullet_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    # recorded | live — which kind of client produced this. A student comparing two tailorings
    # deserves to know one came from a fixture.
    basis: Mapped[str] = mapped_column(String(16), default="live")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        # One current tailoring per posting per upload. Re-tailoring replaces it rather than
        # accumulating rows nobody will ever choose between.
        UniqueConstraint(
            "student_id",
            "job_id",
            "resume_master_id",
            name="uq_tailored_student_job_resume",
        ),
    )
