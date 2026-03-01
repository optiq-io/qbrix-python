from __future__ import annotations

from pydantic import BaseModel


class APIKeyInfo(BaseModel):
    id: str
    name: str
    rate_limit_per_minute: int
    scopes: list[str]
    created_at: float
    last_used_at: float | None = None
    is_active: bool
