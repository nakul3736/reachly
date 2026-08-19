"""link a job to the board that produced it

Closure detection needs to answer "was this posting in the response we just got?", and only the
board identity can. Scoping a sweep by `source` would have one Greenhouse board close every
other Greenhouse board's postings; scoping by `company_name` would break a company running a
second board for a region or a subsidiary.

Nullable, because the aggregator has no board — and because rows ingested before this column
existed have no answer. Those are backfilled on their next successful refresh rather than being
guessed at here: a migration cannot know which of two same-provider boards produced a given row,
and guessing wrong would mis-scope the very sweep this column exists to make safe.

Revision ID: 34f3293a7c0c
Revises: e37586e0cab0
Create Date: 2026-08-18 23:41:12.104553

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "34f3293a7c0c"
down_revision: str | None = "e37586e0cab0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("board_token_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_jobs_board_token_id"), "jobs", ["board_token_id"], unique=False
    )
    op.create_foreign_key(
        "fk_jobs_board_token_id",
        "jobs",
        "board_tokens",
        ["board_token_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_board_token_id", "jobs", type_="foreignkey")
    op.drop_index(op.f("ix_jobs_board_token_id"), table_name="jobs")
    op.drop_column("jobs", "board_token_id")
