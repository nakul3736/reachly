from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    """Identity and credentials.

    Kept separate from `Student`, which holds the search profile: different
    lifecycle, and every later table keys off `student_id` rather than `user_id`.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stored lowercased so case cannot create a second account for one person.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))

    # Seams for later email verification and password reset. Deliberately unused:
    # per ADR 0004 Reachly has no email sender, so implementing these means
    # reintroducing that dependency. Present now so adding them is not a migration
    # against a table with live rows.
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    password_reset_token: Mapped[str | None] = mapped_column(String(128), default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
