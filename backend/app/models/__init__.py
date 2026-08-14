"""SQLAlchemy models.

Importing this package registers every table on `Base.metadata`, so Alembic
autogenerate and the test schema fixture can see them. Add each new model module
to the imports below.

Tables arrive with the features that read them, per
`.kiro/specs/01-profile-and-resume/design.md`. A migration creating tables nothing
queries is a guess awaiting correction.
"""

from app.models.user import User

__all__ = ["User"]
