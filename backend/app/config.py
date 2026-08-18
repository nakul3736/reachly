from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration, read from the environment.

    Secrets carry no defaults. A missing one must stop the process at startup
    rather than let it run with a placeholder — see .kiro/steering/backend.md.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Serves every external call from recorded fixtures. This is the path judges
    # use, so it defaults to the safe value.
    demo_mode: bool = True

    database_url: str

    # No default: a signing key with a fallback means every deployment that forgets
    # to set it shares one, and tokens forged against one work everywhere.
    jwt_secret: str
    jwt_expire_minutes: int = 10080  # one week — a job hunt is not a banking session

    # Aiven's free tier does not document its connection limit, so the pool is
    # sized conservatively and deliberately. See ADR 0008.
    db_pool_size: int = 5
    db_max_overflow: int = 2

    # The documented demo account, per Rule 17. The email has a default because it is
    # published in the README anyway; the password deliberately does not. A fallback
    # would ship a known credential to every deployment that forgot to set one,
    # including any that later holds a real person's data. Seeding refuses without it;
    # the application still boots without it, because seeding is a separate command.
    demo_student_email: str = "demo@reachly.app"
    demo_student_password: str | None = None

    # Browsers block cross-origin requests, and the frontend is served from a different
    # host than the API. Comma-separated so a single environment variable can carry the
    # production origin alongside the local dev server.
    cors_origins: str = "http://localhost:5173"

    # Protects POST /internal/cron/{task}. No default: an unauthenticated endpoint that
    # triggers board refreshes would let anyone drive our outbound request budget. See
    # ADR 0007 — the scheduler is external because Render's free tier stops the process
    # when idle, which silently kills any in-process timer.
    cron_secret: str | None = None

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Inference. Reachly carries its own provider per ADR 0002 — Kiro built this project
    # and does not run inside it. No default key: outside DEMO_MODE a missing key is a
    # configuration error, not a reason to quietly serve fixtures.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # Generous, because structuring a two-page resume is a single large completion and
    # the alternative to waiting is failing an upload the student cannot retry cheaply.
    llm_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
