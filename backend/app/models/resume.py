from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ResumeMaster(Base):
    """An uploaded resume and, later, what was parsed out of it.

    The bytes live in this table rather than on disk. The deployment target has an
    ephemeral filesystem, so a redeploy would silently destroy every upload — and the
    student would not discover it until they tried to tailor an application. A path
    column that works in development is exactly the bug this avoids.
    """

    __tablename__ = "resume_masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )

    # Monotonic per student, starting at 1. Shown to the student, so it has to be a
    # number they can reason about rather than an id.
    version: Mapped[int] = mapped_column(Integer)

    filename: Mapped[str] = mapped_column(String(255))
    byte_size: Mapped[int] = mapped_column(Integer)
    pdf_bytes: Mapped[bytes] = mapped_column(LargeBinary)

    # Populated in ticket 05. Null here means not yet parsed, which is distinct from
    # parsed-and-empty — a distinction the interface needs in order to explain itself.
    parsed_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)

    is_active: Mapped[bool] = mapped_column(default=False)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        # Version numbers are per student, so two students both having a version 1 is
        # correct and one student having two is not.
        UniqueConstraint("student_id", "version", name="uq_resume_student_version"),
        # The one-active invariant, held by the database. Application logic that
        # deactivates before activating is still required, but it is no longer the
        # only thing standing between a bug and two active resumes — and a partial
        # index is the only way to say "unique among the active rows" in Postgres.
        Index(
            "uq_resume_one_active_per_student",
            "student_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )
