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

    # gRPC transport (no effect when transport="http").
    # Defaults mirror /Users/eskinmi/Dev/qbrix/svc/proxy/src/proxysvc/client.py.
    grpc_keepalive_time_ms: int = 30_000
    grpc_keepalive_timeout_ms: int = 10_000
    grpc_http2_max_pings_without_data: int = 0
    grpc_keepalive_permit_without_calls: bool = True
    grpc_use_tls: bool = False

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
