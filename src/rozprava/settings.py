"""Local configuration. Importing this module performs no I/O."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ROZPRAVA_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL", repr=False)
    test_database_url: str | None = Field(
        default=None, validation_alias="TEST_DATABASE_URL", repr=False
    )
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".local/share/rozprava")
    cache_dir: Path = Field(default=None, validate_default=True)

    def __init__(self, _env_file: Path | str | None = ".env", **values: Any):
        super().__init__(_env_file=_env_file, **values)

    @field_validator("cache_dir", mode="before")
    @classmethod
    def cache_path(cls, value: Any, info: ValidationInfo) -> Path:
        return Path(value) if value is not None else info.data["data_dir"] / "cache"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def postgresql_only(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                url = make_url(value)
            except Exception:
                raise ValueError("A postgresql+psycopg database URL is required") from None
            if url.drivername != "postgresql+psycopg" or not url.database:
                raise ValueError("A postgresql+psycopg database URL is required")
        return value

    @model_validator(mode="after")
    def local_paths(self) -> "Settings":
        self.data_dir = self.data_dir.expanduser()
        self.cache_dir = self.cache_dir.expanduser()
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
