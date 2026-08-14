"""Registration and login.

No FastAPI imports: this must be callable from a script or a test without an HTTP
layer. See `.kiro/steering/backend.md`.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import EmailAlreadyRegistered, InvalidCredentials
from app.models.student import Student
from app.models.user import User
from app.security import hash_password, verify_password


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def register(session: AsyncSession, email: str, password: str) -> User:
    """Create the account and its profile in one transaction.

    Both or neither. Creating the profile lazily on first write would mean every
    later feature has to cope with an authenticated user who has no student row.
    """
    user = User(email=normalise_email(email), password_hash=hash_password(password))
    session.add(user)
    try:
        # Flush rather than commit: this assigns the id needed for the profile
        # without ending the transaction, so a failure below rolls back both rows.
        await session.flush()
        session.add(Student(user_id=user.id))
        await session.commit()
    except IntegrityError as exc:
        # Relies on the unique constraint rather than a prior SELECT, so two
        # simultaneous registrations of the same email cannot both succeed.
        await session.rollback()
        raise EmailAlreadyRegistered from exc
    await session.refresh(user)
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    result = await session.execute(select(User).where(User.email == normalise_email(email)))
    user = result.scalar_one_or_none()

    # Verify even when no user was found, so the response time does not reveal
    # whether the email exists.
    stored_hash = user.password_hash if user else _DUMMY_HASH
    matches = verify_password(password, stored_hash)

    if user is None or not matches:
        raise InvalidCredentials
    return user


# A real bcrypt hash of a value nothing authenticates against, used to keep the
# timing of a failed login roughly constant.
_DUMMY_HASH = hash_password("not-a-real-password-placeholder")
