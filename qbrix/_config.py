from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class QbrixConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QBRIX_", env_file=".env")

    base_url: str = "http://localhost:8080"
    api_key: str | None = None
    timeout: float = 5.0
    max_retries: int = 0
    retry_on: tuple[int, ...] = (429, 502, 503, 504)
    retry_base_delay: float = 0.5
    retry_max_delay: float = 30.0
