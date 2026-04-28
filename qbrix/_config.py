from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class QbrixConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QBRIX_", env_file=".env")

    base_url: str = "http://localhost:8080"
    api_key: str | None = None
    timeout: float = 30.0
    max_retries: int = 2
    retry_on: tuple[int, ...] = (429, 502, 503, 504)
    retry_base_delay: float = 0.5
    retry_max_delay: float = 30.0
    http2: bool = False
    max_connections: int | None = None
    max_keepalive_connections: int | None = None

    @field_validator("timeout")
    @classmethod
    def _check_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("timeout must be > 0")
        return v

    @field_validator("max_retries")
    @classmethod
    def _check_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_retries must be >= 0")
        return v

    @field_validator("retry_base_delay")
    @classmethod
    def _check_base_delay(cls, v: float) -> float:
        if v < 0:
            raise ValueError("retry_base_delay must be >= 0")
        return v
