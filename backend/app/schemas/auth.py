from pydantic import BaseModel, EmailStr, Field

from app.security import BCRYPT_MAX_BYTES

# Long enough to matter, short enough not to push people toward a sticky note.
MIN_PASSWORD_LENGTH = 8


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=BCRYPT_MAX_BYTES)


class TokenResponse(BaseModel):
    access_token: str
    # The OAuth bearer scheme name, not a credential — hence the suppression.
    token_type: str = "bearer"  # noqa: S105


class UserResponse(BaseModel):
    """Deliberately omits the credential columns.

    A response model rather than the ORM object, so adding a column to `User` can
    never start leaking it. See `.kiro/steering/backend.md`.
    """

    id: int
    email: EmailStr
