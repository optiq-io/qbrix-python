from __future__ import annotations

from typing import Generic, Literal, TypeVar, Union

T = TypeVar("T")


class NotGiven:
    """Sentinel for an argument the caller did not pass.

    Distinct from ``None``, which several fields use as a meaningful value —
    ``gate.update(exp, default_arm_id=None)`` clears the default arm, while
    omitting the argument leaves it as stored.
    """

    def __bool__(self) -> Literal[False]:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN = NotGiven()

NotGivenOr = Union[T, NotGiven]


class LazyProxy(Generic[T]):
    """Defers instantiation of a resource until first attribute access."""

    def __init__(self) -> None:
        object.__setattr__(self, "_proxied", None)

    def __load__(self) -> T:
        raise NotImplementedError

    def __getattr__(self, name: str) -> object:
        proxied = object.__getattribute__(self, "_proxied")
        if proxied is None:
            proxied = self.__load__()
            object.__setattr__(self, "_proxied", proxied)
        return getattr(proxied, name)

    def __as_proxied__(self) -> "LazyProxy[T]":
        return self
