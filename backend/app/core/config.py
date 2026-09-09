"""Application settings, loaded from environment / .env via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "INF2003 Project API"
    debug: bool = False

    # Postgres — SQLAlchemy/Alembic use the URL as-is; asyncpg pools are built from it.
    postgres_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/app"

    # MongoDB — consumed by Motor.
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "app"


@lru_cache
def get_settings() -> Settings:
    return Settings()
