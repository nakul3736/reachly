from datetime import datetime

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Student(Base):
    """What the student is looking for.

    Every field is nullable or empty by default. A profile is built up over time, and
    a value Reachly invented to fill a column would be indistinguishable from one the
    student supplied — which is the failure mode ADR 0006 exists to prevent.

    `years_experience` of None is not 0. None means unstated; 0 is a claim. Scoring
    must be able to tell them apart.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Unique: one profile per account. Enforced here rather than in application code
    # so a second row cannot be created by a concurrent request.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    name: Mapped[str | None] = mapped_column(String(200), default=None)
    target_role: Mapped[str | None] = mapped_column(String(200), default=None)
    years_experience: Mapped[int | None] = mapped_column(Integer, default=None)

    # Arrays rather than a joined table: these are short lists read as a whole and
    # never queried independently. A join table would add a migration and a
    # relationship for no gain.
    locations: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), default=list, server_default="{}"
    )
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), default=list, server_default="{}"
    )

    # Free-form: github, portfolio, and whatever else a student has. Shape is not
    # fixed because the outreach draft only ever reads it as a whole.
    links: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
