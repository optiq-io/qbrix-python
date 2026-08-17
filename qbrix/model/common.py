from __future__ import annotations

from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

T = TypeVar("T")


class Context(BaseModel):
    """the request being served, as the strategy and the gate see it."""

    id: str = Field(
        ...,
        description="stable identifier for the request source, e.g. a user or "
        "session id. drives deterministic feature-gate rollout.",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description='named request properties, e.g. {"device": "mobile", '
        '"price": 20}. encoded server-side against the experiment\'s declared '
        "context schema. this is the way to give a contextual strategy features.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="free-form key-value pairs for feature-gate targeting. "
        "never read by the strategy itself.",
    )
    vector: list[int | float] | None = Field(
        default=None,
        description="pre-encoded feature vector; its width must equal the "
        "experiment's dim. prefer `properties` and let qbrix own the encoding. "
        "reach for this when you already hold a learned embedding, when the "
        "feature is a quantity you derive yourself (a similarity score, a model "
        "prediction, a PCA component), or when migrating an existing contextual "
        "experiment that needs byte-identical encoding.",
    )

    @model_validator(mode="after")
    def _one_context_channel(self) -> Context:
        if self.vector is not None and self.properties is not None:
            raise ValueError("send context.vector or context.properties, not both")
        return self


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return len(self.items) >= self.limit
