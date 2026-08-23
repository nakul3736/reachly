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

    # Pinned, not `gemini-flash-latest`. Two reasons, both observed rather than assumed:
    # `gemini-2.5-flash` now 404s with "no longer available to new users", so an unpinned
    # guess goes stale; and in testing the moving alias returned 503 in the same minute
    # that two pinned models returned 200. A judged window is the wrong time for the model
    # to change underneath us.
    # Changed from gemini-3.6-flash on 23 Aug after it began returning 429 for every request while
    # the same key got 200 from 3.5-flash in the same second. Measured, not assumed:
    #
    #   gemini-3.6-flash -> 429 "You exceeded your current quota"
    #   gemini-3.5-flash -> 200
    #   gemini-2.5-flash -> 404 no longer available
    #   gemini-2.0-flash -> 404 no longer available
    #   gemini-1.5-flash -> 404 not found
    #
    # Free-tier quotas are per model, so the newest model is not the one with room in it.
    gemini_model: str = "gemini-3.5-flash"

    # Generous, because structuring a two-page resume is a single large completion and
    # the alternative to waiting is failing an upload the student cannot retry cheaply.
    llm_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
