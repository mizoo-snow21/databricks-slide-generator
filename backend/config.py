from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    databricks_host: str = ""
    databricks_token: str = ""
    uc_catalog: str = "genie_slide"
    uc_schema: str = "app"
    gslides_builder_path: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
