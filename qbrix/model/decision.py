from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import Field


class Option(BaseModel):
    key: str
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    # None only when qbrix couldn't be reached and no offline option was given.
    option: Option | None
    # None when the answer can't learn: a draft or paused loop, or offline.
    request_id: str | None = None
    # live, draft or paused from the server; offline from the SDK.
    reason: str


class Settings(BaseModel):
    offline: Option | None = None
    timeout: float | None = None
    max_retries: int | None = None


class Outcome(BaseModel):
    id: str
    at: datetime
