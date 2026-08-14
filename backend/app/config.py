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

    # Aiven's free tier does not document its connection limit, so the pool is
    # sized conservatively and deliberately. See ADR 0008.
    db_pool_size: int = 5
    db_max_overflow: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
