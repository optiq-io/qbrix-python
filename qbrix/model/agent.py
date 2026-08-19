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
    # None when the experiment is paused, or when the SDK resolved a client-side
    # fallback — neither case has a server-minted feedback token.
    request_id: str | None = None
    is_default: bool
    # True only when select() never reached the proxy (timeout/connection/5xx)
    # and the SDK resolved the caller-declared `fallback` arm locally. Distinct
    # from is_default, which reflects a real, server-side gate decision.
    is_fallback: bool = False


class FeedbackRequest(BaseModel):
    request_id: str
    reward: int | float


class FeedbackResponse(BaseModel):
    accepted: bool
