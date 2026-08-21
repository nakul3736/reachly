"""read skills out of job descriptions

Three columns rather than one. The set of skills is the answer; the basis records which reading
produced it, because a student comparing two scores deserves to know one posting was read more
thoroughly than the other; and the timestamp records that a reading finished at all.

The timestamp is what makes an outage retryable. Enrichment writes the vocabulary result even
when
the model is unreachable, so without a separate "did this finish" column a failed batch would be
indistinguishable from a completed one and the posting would never be read again.

Revision ID: a4cdc59cdd17
Revises: 34f3293a7c0c
Create Date: 2026-08-20 20:27:15.486922
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4cdc59cdd17"
down_revision: str | None = "34f3293a7c0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "extracted_skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column("jobs", sa.Column("skills_basis", sa.String(length=16), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("skills_extracted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "skills_extracted_at")
    op.drop_column("jobs", "skills_basis")
    op.drop_column("jobs", "extracted_skills")
