from __future__ import annotations

from pydantic import BaseModel

from qbrix.model.common import Context


class SelectRequest(BaseModel):
    experiment_id: str
    context: Context


class SelectedArm(BaseModel):
    id: str
    name: str
    index: int


class SelectResponse(BaseModel):
    arm: SelectedArm
    # None when the experiment is paused — the proxy mints no feedback token.
    request_id: str | None = None
    is_default: bool


class FeedbackRequest(BaseModel):
    request_id: str
    reward: int | float


class FeedbackResponse(BaseModel):
    accepted: bool
