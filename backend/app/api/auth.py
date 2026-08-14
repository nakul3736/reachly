from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import NotAuthenticated
from app.models.user import User
from app.schemas.auth import Credentials, TokenResponse, UserResponse
from app.security import InvalidToken, create_access_token, read_access_token
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """The authenticated user, or `NotAuthenticated`.

    Every failure — missing header, wrong scheme, forged signature, expired token,
    or a token naming a user who no longer exists — produces the same refusal.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise NotAuthenticated

    try:
        user_id = read_access_token(authorization.split(" ", 1)[1].strip())
    except InvalidToken as exc:
        raise NotAuthenticated from exc

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise NotAuthenticated
    return user


CurrentUser = Annotated[User, Depends(current_user)]


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(credentials: Credentials, session: SessionDep) -> TokenResponse:
    user = await auth_service.register(session, credentials.email, credentials.password)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(credentials: Credentials, session: SessionDep) -> TokenResponse:
    user = await auth_service.authenticate(session, credentials.email, credentials.password)
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> User:
    return user
