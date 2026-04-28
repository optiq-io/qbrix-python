from __future__ import annotations

from pydantic import BaseModel


class APIKeyInfo(BaseModel):
    """API key metadata (no secret key value)."""

    id: str
    name: str
    rate_limit_per_minute: int
    scopes: list[str]
    created_at: float
    last_used_at: float | None = None
    is_active: bool


class APIKeyCreated(BaseModel):
    """Response when creating or rotating an API key — includes the plain-text key."""

    id: str
    name: str
    key: str
    rate_limit_per_minute: int
    scopes: list[str]
    created_at: float
    is_active: bool


class APIKeyUsage(BaseModel):
    """Rate-limit usage for a single API key."""

    current_minute_usage: int
    rate_limit_per_minute: int
