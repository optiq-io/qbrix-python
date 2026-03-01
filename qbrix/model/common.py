from __future__ import annotations

from typing import Generic
from typing import TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class Context(BaseModel):
    id: str
    vector: list[int | float] | None = None
    metadata: dict[str, str] | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return len(self.items) >= self.limit
