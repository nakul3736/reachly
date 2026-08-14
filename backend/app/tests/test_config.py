"""Settings.

A secret with a default is worse than a missing one: the process starts, appears
healthy, and behaves wrongly. See .kiro/steering/backend.md.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_missing_database_url_fails_and_names_the_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as caught:
        # _env_file=None so a developer's local .env cannot mask the failure.
        Settings(_env_file=None)

    assert "database_url" in str(caught.value).lower()


def test_demo_mode_defaults_to_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """The keyless path is the default.

    DEMO_MODE=false is the opt-in, so forgetting to set it cannot cause the app to
    start reaching for API keys it does not have.
    """
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")

    settings = Settings(_env_file=None)

    assert settings.demo_mode is True
