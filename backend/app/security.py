"""Password hashing and access tokens.

bcrypt is used directly rather than through passlib, which raises on bcrypt 4.1+
because it reads a `__about__` attribute that was removed.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings

_ALGORITHM = "HS256"

# bcrypt silently truncates at 72 bytes. Rejecting longer input is honest; letting
# it through would mean two different passwords authenticating the same account.
BCRYPT_MAX_BYTES = 72


class InvalidToken(Exception):
    """The token is absent, malformed, expired, or signed with another key."""


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # A malformed stored hash must not authenticate anyone.
        return False


def create_access_token(subject: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def read_access_token(token: str) -> int:
    """Return the user id a token asserts, or raise `InvalidToken`.

    Every failure mode collapses to one exception: the caller has no legitimate
    use for the difference between an expired token and a forged one, and telling
    them apart in a response would leak information.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise InvalidToken from exc
