"""add students table

Revision ID: da36f6d8d38d
Revises: 0308b4a26e14
Create Date: 2026-08-13 20:41:50.878084

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "da36f6d8d38d"
down_revision: str | None = "0308b4a26e14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Nullable by design: a profile is built up over time, and a value invented
        # to fill a column would be indistinguishable from one the student supplied.
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("target_role", sa.String(length=200), nullable=True),
        # Null is unstated, which is not the same as zero. Scoring must distinguish.
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column(
            "locations",
            sa.ARRAY(sa.String(length=120)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "skills",
            sa.ARRAY(sa.String(length=80)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "links",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # CASCADE: deleting an account removes its profile rather than orphaning it.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique: one profile per account, enforced by the database so a concurrent
    # request cannot create a second.
    op.create_index(op.f("ix_students_user_id"), "students", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_students_user_id"), table_name="students")
    op.drop_table("students")
