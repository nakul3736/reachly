"""widen provider supplied job text columns

Provider-supplied display text has no length we get to assume. One real Muse posting listed in
dozens of cities produced 820 characters of location against a `varchar(500)`, which failed the
entire refresh rather than a single posting.

Note the asymmetry: **the upgrade is safe and the downgrade can lose data.** Narrowing back to
`varchar` truncates any row that has since exceeded the old limit, and Postgres will refuse
rather than silently cut, so a downgrade against a populated database can fail. That is the
correct behaviour — losing a student's location text quietly would be worse — but it means the
downgrade is only reliable on a database that has not ingested since.

Revision ID: e37586e0cab0
Revises: a79844b0be1d
Create Date: 2026-08-18 23:22:08.838686

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e37586e0cab0"
down_revision: str | None = "a79844b0be1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "jobs",
        "company_name",
        existing_type=sa.VARCHAR(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "title",
        existing_type=sa.VARCHAR(length=500),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "location_raw",
        existing_type=sa.VARCHAR(length=500),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "jobs",
        "apply_url",
        existing_type=sa.VARCHAR(length=1000),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "jobs",
        "apply_url",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=1000),
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "location_raw",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=500),
        existing_nullable=True,
    )
    op.alter_column(
        "jobs",
        "title",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=500),
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "company_name",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
