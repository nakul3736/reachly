"""Seed the documented demo account.

    python -m app.seed

Rule 17 requires judges to be given working credentials, and Round One screening rewards
a project that works on first contact — an empty form demonstrates nothing.

Two properties shape the implementation:

* **Idempotent.** A redeploy runs this again. Creating a second account would fail on the
  unique email constraint and break the deploy; adding a resume version every release
  would make the demo drift.
* **Safe beside real data.** It touches one documented account and nothing else. There is
  no truncate, no reset, and no "clean the database first" step, because this runs against
  the deployed database.
"""

import asyncio
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.fixtures.demo_resume import DEMO_RESUME_FILENAME, demo_resume_bytes
from app.adapters.resume_parser import get_resume_parser
from app.config import get_settings
from app.db import dispose_engine, get_session_factory
from app.errors import DomainError
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.user import User
from app.security import hash_password
from app.seed_boards import seed_boards


class DemoCredentialsMissing(DomainError):
    """`DEMO_STUDENT_PASSWORD` is not set.

    Raised rather than defaulted. A hardcoded fallback would be a published credential on
    every deployment that forgot to configure one.
    """

    status_code = 500
    code = "demo_credentials_missing"
    message = "Set DEMO_STUDENT_PASSWORD before seeding the demo account."


@dataclass(frozen=True)
class SeedResult:
    """What the run did.

    Reported because a human runs this during a deploy, and silence leaves you unable to
    tell a successful seed from a no-op.
    """

    email: str
    created: bool
    resume_versions: int


# A realistic new graduate, consistent with the fictional resume in
# app/adapters/fixtures/demo_resume.pdf — the skills below all appear in it, so the demo
# account does not claim anything its own resume cannot evidence.
DEMO_PROFILE = {
    "name": "Alex Rivera",
    "target_role": "Backend Engineer",
    "locations": ["Halifax, NS", "Toronto, ON", "Remote"],
    "years_experience": 1,
    "skills": [
        "Python",
        "TypeScript",
        "SQL",
        "FastAPI",
        "React",
        "PostgreSQL",
        "Docker",
        "CI/CD",
    ],
    "links": {"github": "https://github.com/example", "portfolio": "https://example.dev"},
}


async def seed_demo_student(session: AsyncSession) -> SeedResult:
    """Ensure the demo account exists, with a profile and a parsed resume."""
    settings = get_settings()
    if not settings.demo_student_password:
        raise DemoCredentialsMissing

    email = settings.demo_student_email.strip().lower()

    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if existing is not None:
        # Already seeded. Deliberately does not overwrite: if someone has been clicking
        # around the demo account, resetting it mid-session would be more confusing than
        # leaving it. Reseeding from scratch is a database reset, which is a decision for
        # a human rather than a side effect of deploying.
        versions = len(
            list(
                (
                    await session.execute(
                        select(ResumeMaster).join(Student).where(Student.user_id == existing.id)
                    )
                ).scalars()
            )
        )
        return SeedResult(email=email, created=False, resume_versions=versions)

    user = User(
        email=email,
        password_hash=hash_password(settings.demo_student_password),
        is_verified=True,
    )
    session.add(user)
    await session.flush()

    student = Student(user_id=user.id, **DEMO_PROFILE)
    session.add(student)
    await session.flush()

    pdf_bytes = demo_resume_bytes()
    parsed = await get_resume_parser().parse(pdf_bytes)
    session.add(
        ResumeMaster(
            student_id=student.id,
            version=1,
            filename=DEMO_RESUME_FILENAME,
            byte_size=len(pdf_bytes),
            pdf_bytes=pdf_bytes,
            parsed_json=parsed.model_dump(mode="json"),
            is_active=True,
        )
    )

    await session.commit()
    return SeedResult(email=email, created=True, resume_versions=1)


async def _main() -> int:
    """Entry point for `python -m app.seed`.

    Reports failure as a message and a non-zero exit code rather than a traceback. This
    runs as a deploy step, where a stack trace is noise and the exit code is what the
    surrounding script reads.

    Boards are seeded before the demo account, and independently of it. The demo account
    needs credentials supplied by the environment and legitimately fails without them; the
    board registry needs nothing and is what makes the product show real jobs. Seeding
    them together would mean a deployment without demo credentials also had an empty job
    index, which is a much worse failure than a missing test login.
    """
    boards = 0
    try:
        async with get_session_factory()() as session:
            boards = (await seed_boards(session)).created
            result = await seed_demo_student(session)
    except DemoCredentialsMissing as error:
        print(f"{boards} board(s) registered")
        print(f"seed failed: {error.message}", file=sys.stderr)
        return 1
    finally:
        await dispose_engine()

    verb = "created" if result.created else "already present"
    print(f"{boards} board(s) registered")
    print(f"demo account {verb}: {result.email} ({result.resume_versions} resume version(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
