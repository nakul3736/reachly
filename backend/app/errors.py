"""Domain errors and the response envelope.

The interface distinguishes cases the student can act on differently — an unreadable
file is not an unavailable provider — so every error carries a stable
machine-readable code, not only prose. See `.kiro/steering/backend.md`.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """An error with a stable code the frontend can branch on."""

    status_code = 400
    code = "domain_error"
    message = "The request could not be completed."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class EmailAlreadyRegistered(DomainError):
    status_code = 409
    code = "email_already_registered"
    message = "That email already has an account. Try logging in instead."


class InvalidCredentials(DomainError):
    """Deliberately identical for an unknown email and a wrong password.

    Distinguishing them would let anyone discover whether a given person has an
    account here by submitting one request.
    """

    status_code = 401
    code = "invalid_credentials"
    message = "That email and password do not match an account."


class NotAuthenticated(DomainError):
    status_code = 401
    code = "not_authenticated"
    message = "Sign in to continue."


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, DomainError)
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )
