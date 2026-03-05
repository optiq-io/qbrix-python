from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


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
