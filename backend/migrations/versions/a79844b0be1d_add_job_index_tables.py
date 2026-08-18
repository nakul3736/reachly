"""add job index tables

Revision ID: a79844b0be1d
Revises: 772d886c1fd2
Create Date: 2026-08-18 19:31:13.036475

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a79844b0be1d"
down_revision: str | None = "772d886c1fd2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "board_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "token", name="uq_board_provider_token"),
    )
    op.create_index(
        op.f("ix_board_tokens_provider"), "board_tokens", ["provider"], unique=False
    )

    op.create_table(
        "dedup_verdicts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fingerprint_low", sa.String(length=64), nullable=False),
        sa.Column("fingerprint_high", sa.String(length=64), nullable=False),
        sa.Column("same_job", sa.Boolean(), nullable=False),
        sa.Column("decided_by", sa.String(length=16), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint_low", "fingerprint_high", name="uq_dedup_pair"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_job_id", sa.String(length=128), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("location_raw", sa.String(length=500), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("is_remote", sa.Boolean(), nullable=True),
        sa.Column("role_family", sa.String(length=64), nullable=True),
        sa.Column("seniority", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("apply_url", sa.String(length=1000), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("canonical_job_id", sa.Integer(), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["canonical_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_job_id", name="uq_job_source_id"),
    )
    op.create_index(
        "ix_job_open_recent", "jobs", ["closed_at", "first_seen_at"], unique=False
    )
    op.create_index(
        op.f("ix_jobs_canonical_job_id"), "jobs", ["canonical_job_id"], unique=False
    )
    op.create_index(op.f("ix_jobs_closed_at"), "jobs", ["closed_at"], unique=False)
    op.create_index(op.f("ix_jobs_company_name"), "jobs", ["company_name"], unique=False)
    op.create_index(
        op.f("ix_jobs_content_fingerprint"), "jobs", ["content_fingerprint"], unique=False
    )
    op.create_index(op.f("ix_jobs_country"), "jobs", ["country"], unique=False)
    op.create_index(op.f("ix_jobs_role_family"), "jobs", ["role_family"], unique=False)
    op.create_index(op.f("ix_jobs_seniority"), "jobs", ["seniority"], unique=False)
    op.create_index(op.f("ix_jobs_source"), "jobs", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_source"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_seniority"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_role_family"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_country"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_content_fingerprint"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_company_name"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_closed_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_canonical_job_id"), table_name="jobs")
    op.drop_index("ix_job_open_recent", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("dedup_verdicts")
    op.drop_index(op.f("ix_board_tokens_provider"), table_name="board_tokens")
    op.drop_table("board_tokens")
