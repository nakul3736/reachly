"""add resume masters table

Revision ID: 772d886c1fd2
Revises: da36f6d8d38d
Create Date: 2026-08-13 20:56:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "772d886c1fd2"
down_revision: str | None = "da36f6d8d38d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_masters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        # The bytes live here rather than on disk. The deployment target has an
        # ephemeral filesystem, so a redeploy would destroy every upload silently.
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        # Null means not yet parsed, which is distinct from parsed-and-empty. The
        # interface needs that difference to explain itself. Populated in ticket 05.
        sa.Column("parsed_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Version numbers are per student, so two students both having a version 1 is
        # correct and one student having two of the same is not.
        sa.UniqueConstraint("student_id", "version", name="uq_resume_student_version"),
    )
    op.create_index(
        op.f("ix_resume_masters_student_id"),
        "resume_masters",
        ["student_id"],
        unique=False,
    )
    # The one-active invariant, held by the database rather than by application code
    # alone. Scoped to student_id: a global unique index on is_active would allow
    # exactly one student in the whole system to have an active resume, a failure that
    # only appears once there is a second user.
    op.create_index(
        "uq_resume_one_active_per_student",
        "resume_masters",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_resume_one_active_per_student",
        table_name="resume_masters",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_index(op.f("ix_resume_masters_student_id"), table_name="resume_masters")
    op.drop_table("resume_masters")
