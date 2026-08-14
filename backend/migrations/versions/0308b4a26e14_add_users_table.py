"""add users table

Revision ID: 0308b4a26e14
Revises: fde1c24e1c3d
Create Date: 2026-08-13 20:28:52.667120

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0308b4a26e14"
down_revision: str | None = "fde1c24e1c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("password_reset_token", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique rather than merely indexed: email identity is enforced by the
    # database, so two simultaneous registrations cannot both succeed.
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
