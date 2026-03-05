from __future__ import annotations

from typing import Generic
from typing import TypeVar
from typing import List
from typing import Dict

from pydantic import BaseModel


T = TypeVar("T")


class Context(BaseModel):
    id: str
    vector: List[int | float] | None = None
    metadata: Dict[str, str] | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return len(self.items) >= self.limit
