"""discard scores computed by the previous keyword arithmetic

Revision ID: c4a1b2d3e5f6
Revises: 31dfd5f52bf0
Create Date: 2026-08-23

The keyword component's tokeniser now requires three characters rather than two, so every stored
`match_scores` row holds the result of a calculation that no longer exists. The rows are a cache,
not a record — nothing references them and they are rebuilt lazily on the next page render — so the
honest response to changing the arithmetic is to throw them away rather than leave a student's feed
showing one number and the score report showing another.

This is deliberately a delete and not a schema change. `alembic check` compares the schema against
the models and will never notice that cached values have gone stale, which is precisely why the
invalidation has to be written down here where it runs on deploy.

Irreversible in the sense that matters: downgrade cannot recreate rows it did not keep, and does not
need to, because the next request recomputes them.
"""

from alembic import op

revision = "c4a1b2d3e5f6"
down_revision = "31dfd5f52bf0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM match_scores")


def downgrade() -> None:
    # Nothing to restore. The rows were derived, and the previous arithmetic is gone from the code.
    pass
