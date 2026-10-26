from __future__ import annotations

from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

T = TypeVar("T")


class Context(BaseModel):
    """what the app knows about the request a decision is for."""

    unit: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="who or what sees the decision, e.g. a user or session id, "
        "stable for as long as its outcome can arrive.",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description='named request properties, e.g. {"device": "mobile", '
        '"plan": "pro"}. recorded with every decision.',
    )

    @field_validator("unit")
    @classmethod
    def _unit_not_blank(cls, unit: str) -> str:
        if not unit.strip():
            raise ValueError("context.unit must not be blank")
        return unit


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return len(self.items) >= self.limit
