from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Job(Base):
    """One posting, as one source published it.

    The index is shared across every student rather than fetched per session, per ADR
    0005: a per-student fetch would multiply provider requests by the user count, make
    rate limits a function of popularity, and make closure detection impossible to reason
    about since no student would ever see the whole picture.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # greenhouse | lever | ashby | muse.
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_job_id: Mapped[str] = mapped_column(String(128))

    # The three columns below hold text a provider chose, and are deliberately unbounded.
    #
    # A cap here can only ever produce a 500 in the refresh, and it did: one real Muse posting
    # listed in dozens of cities produced 820 characters of location against a varchar(500),
    # which failed the whole run rather than one posting. There is no length we get to assume
    # about somebody else's field, truncating would lose what story 21 says is shown as written,
    # and Postgres charges nothing for text over varchar.
    company_name: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text)
    location_raw: Mapped[str | None] = mapped_column(Text, default=None)

    # Derived in ticket 04. Null means not yet classified, which is distinct from
    # classified-as-unknown — the interface needs that difference to explain itself.
    country: Mapped[str | None] = mapped_column(String(2), default=None, index=True)
    is_remote: Mapped[bool | None] = mapped_column(Boolean, default=None)
    role_family: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    seniority: Mapped[str | None] = mapped_column(String(32), default=None, index=True)

    description: Mapped[str] = mapped_column(Text)
    apply_url: Mapped[str] = mapped_column(Text)

    # As the source reported it, and frequently absent. Distinct from first_seen_at, which
    # is when Reachly noticed: a job posted before we registered its board would otherwise
    # look brand new.
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Which registry row produced this posting. Null for the aggregator, which has no board.
    #
    # Closure detection is why this exists rather than the sweep being scoped by `source` or by
    # `company_name`. By source, Figma's refresh would close Linear's entire listing — both are
    # Greenhouse, and neither appears in the other's response. By company name, a firm running a
    # second board for a region or subsidiary would have each close the other. Only the board
    # identity answers "was this posting in the response we just got?".
    board_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("board_tokens.id", ondelete="SET NULL"), default=None, index=True
    )

    # Set when a posting stops appearing in a successful board refresh. The row is kept:
    # a student's application must still resolve to the job it was made against, so
    # history cannot be allowed to develop holes.
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )

    # True for a company's own board, false for an aggregator. Not cosmetic: it decides
    # which record wins during dedup and whether absence from a refresh means anything.
    is_verified: Mapped[bool] = mapped_column(default=True)

    # Null means this row is canonical. Set means it is an alias of another row, and it
    # never appears as its own feed entry.
    canonical_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), default=None, index=True
    )

    # Content-derived identity, over normalised company, title and location. Never a
    # provider id, because no two providers share one — and never positional, for the
    # same reason bullet ids are not: a positional identifier keeps resolving while
    # pointing at something else.
    content_fingerprint: Mapped[str | None] = mapped_column(
        String(64), default=None, index=True
    )

    # Skills read out of the description, per ADR 0011. Stored on the posting rather than
    # computed per render because the reading is the same for every student, and the feed is
    # forbidden from making model calls.
    extracted_skills: Mapped[list[str] | None] = mapped_column(JSONB, default=None)

    # vocabulary | model. Which reading produced the set above. Shown in the interface, because
    # a student comparing two scores deserves to know one posting was read more thoroughly.
    skills_basis: Mapped[str | None] = mapped_column(String(16), default=None)

    # Null means no reading has finished. Deliberately not set when enrichment fails, so an
    # outage is retried rather than remembered as a completed reading — the same rule that keeps
    # a failed board fetch from closing anything.
    skills_extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # The experience requirement, parsed once and kept.
    #
    # This is cached for the same reason the skills are: reading it is student-independent, and
    # measurement showed it was 0.52s of the 1.22s spent scoring 200 postings — recomputed for
    # every student, on a free instance with a tenth of a CPU, for an answer that cannot differ
    # between them. Caching it turned the scored feed from tens of seconds into a fraction of one.
    #
    # `experience_parsed_at` distinguishes "parsed and found nothing" from "never parsed", which
    # matters because unstated is a real answer the score renders differently from silence.
    required_years: Mapped[float | None] = mapped_column(default=None)
    requirement_basis: Mapped[str | None] = mapped_column(String(16), default=None)
    requirement_phrase: Mapped[str | None] = mapped_column(String(200), default=None)
    experience_parsed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    __table_args__ = (
        # The constraint that makes ingestion idempotent. A refresh re-run after a crash
        # must not double the index, and this is a constraint rather than a
        # check-then-insert because two concurrent refreshes would both pass the check.
        UniqueConstraint("source", "source_job_id", name="uq_job_source_id"),
        # The feed's default query: open jobs, newest first.
        Index("ix_job_open_recent", "closed_at", "first_seen_at"),
    )


class DedupVerdict(Base):
    """A permanent answer to "are these two postings the same job?".

    Permanent because the expensive verdicts come from the one inference call this feature
    permits, and the answer cannot change: two fixed pieces of text are either the same
    job or they are not.
    """

    __tablename__ = "dedup_verdicts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Named low and high rather than a and b so that a caller cannot accidentally cache
    # one comparison twice under opposite orderings. The pair is sorted before storage.
    fingerprint_low: Mapped[str] = mapped_column(String(64))
    fingerprint_high: Mapped[str] = mapped_column(String(64))

    same_job: Mapped[bool] = mapped_column(Boolean)

    # exact | fuzzy | inference. Kept so a change to the fuzzy threshold can be reapplied
    # without discarding the verdicts that were paid for.
    decided_by: Mapped[str] = mapped_column(String(16))

    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("fingerprint_low", "fingerprint_high", name="uq_dedup_pair"),
    )
