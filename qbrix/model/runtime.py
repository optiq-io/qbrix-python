from __future__ import annotations

from pydantic import BaseModel


class ServiceHealth(BaseModel):
    service: str
    status: str


class StreamSize(BaseModel):
    len: int
