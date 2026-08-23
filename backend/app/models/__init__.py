"""SQLAlchemy models.

Importing this package registers every table on `Base.metadata`, so Alembic
autogenerate and the test schema fixture can see them. Add each new model module
to the imports below.

**Forgetting to is not a small mistake, and the test suite will not catch it.** Two models were
added here late and left out of this list; autogenerate saw no new tables and wrote two migrations
whose bodies were `pass`. Every test still passed, because the test fixture builds the schema from
`Base.metadata` — which the tests import directly — while the deployment builds it from migrations.
The failure only appeared in the deployed app, as a 500 the browser reported as "Failed to fetch".

`alembic check` was blind for the same reason: it compares migrations against this metadata, so a
model missing here is missing from both sides of the comparison and the two agree perfectly.

Tables arrive with the features that read them, per
`.kiro/specs/01-profile-and-resume/design.md`. A migration creating tables nothing
queries is a guess awaiting correction.
"""

from app.models.application import Application, ApplicationStatus
from app.models.board_token import BoardToken
from app.models.job import DedupVerdict, Job
from app.models.match_score import MatchScore
from app.models.outreach_draft import OutreachDraftRow
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.tailored_resume import TailoredResume
from app.models.user import User

__all__ = [
    "Application",
    "ApplicationStatus",
    "BoardToken",
    "DedupVerdict",
    "Job",
    "MatchScore",
    "OutreachDraftRow",
    "ResumeMaster",
    "Student",
    "TailoredResume",
    "User",
]
