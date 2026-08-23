from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MatchScore(Base):
    """One posting's score against one student, as computed from one resume version.

    Scores are computed for the page a student is looking at and then kept. Computing the whole
    index per student would be the most expensive operation in the application — 4,437 rows each,
    almost all of it for postings nobody scrolls to.

    **The resume version is part of the identity, and that is what makes invalidation free.**
    Uploading a new resume deletes nothing: the old rows simply stop matching the key, the next
    render computes fresh ones, and the old rows remain true about the resume they describe. The
    alternative — a nullable `is_stale` flag, or deleting on upload — needs a process that
    remembers to run, and a score that silently describes a replaced resume is a lie the student
    has no way to detect.
    """

    __tablename__ = "match_scores"

    id: Mapped[int] = mapped_column(primary_key=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    resume_master_id: Mapped[int] = mapped_column(
        ForeignKey("resume_masters.id", ondelete="CASCADE"), index=True
    )

    total: Mapped[int] = mapped_column(Integer)

    # Stored separately rather than derived from the total, because the decomposition is the
    # product: ADR 0003 says sub-scores are shown rather than rolled into an opaque number, and a
    # total cannot be decomposed back into the parts that produced it.
    skill_points: Mapped[int] = mapped_column(Integer)
    experience_points: Mapped[int] = mapped_column(Integer)
    keyword_points: Mapped[int] = mapped_column(Integer)
    freshness_points: Mapped[int] = mapped_column(Integer)

    # Why each component scored what it did. `unstated` is not the same as zero and the interface
    # renders it differently, so the state has to survive the round trip to the database.
    skill_state: Mapped[str] = mapped_column(String(16))
    experience_state: Mapped[str] = mapped_column(String(16))
    keyword_state: Mapped[str] = mapped_column(String(16))
    freshness_state: Mapped[str] = mapped_column(String(16))

    # The score's receipt: which of the posting's skills the student has and which they do not.
    # Stored rather than recomputed so the explanation cannot drift from the number it explains
    # when the vocabulary or the enrichment changes underneath it.
    matched_skills: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    missing_skills: Mapped[list[str] | None] = mapped_column(JSONB, default=None)

    # What the experience component read, and the words it read it from. The phrase is what lets
    # the interface show the student the sentence rather than only the number.
    required_years: Mapped[float | None] = mapped_column(default=None)
    requirement_basis: Mapped[str | None] = mapped_column(String(16), default=None)
    requirement_phrase: Mapped[str | None] = mapped_column(String(200), default=None)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "job_id",
            "resume_master_id",
            name="uq_match_score_student_job_resume",
        ),
        # The feed's query: this student's scores, highest first.
        Index("ix_match_score_student_total", "student_id", "total"),
    )
