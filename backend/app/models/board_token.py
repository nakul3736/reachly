from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BoardToken(Base):
    """A company job board Reachly knows how to fetch.

    This is a table rather than a list of company names transformed into URLs at runtime
    because spike 001 measured that the transformation does not work: 12 of 20 plausible
    Lever slugs returned 404. The tokens are not derivable from company names, so they
    have to be stored, and storing them makes adding a company a data change rather than
    a deployment.
    """

    __tablename__ = "board_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)

    # greenhouse | lever | ashby. Aggregators are not boards and are not registered here:
    # The Muse is one endpoint for every company, not one per company.
    provider: Mapped[str] = mapped_column(String(32), index=True)
    token: Mapped[str] = mapped_column(String(128))

    company_name: Mapped[str] = mapped_column(String(255))

    # Set false to stop fetching a board without losing the record of having known it,
    # and without losing its jobs.
    active: Mapped[bool] = mapped_column(default=True)

    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Deliberately separate from last_fetched_at. A board fetched every day and failing
    # every day would otherwise look healthy, which is the silent failure this pair of
    # columns exists to make loud.
    last_succeeded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Drives backoff in ticket 07. A permanently dead company should not consume the
    # refresh window at full rate every day.
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), default=None)

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        # The pair, not the token alone. The same slug can exist on two providers and
        # they are different boards.
        UniqueConstraint("provider", "token", name="uq_board_provider_token"),
    )
