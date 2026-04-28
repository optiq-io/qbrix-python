from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qbrix._client import Qbrix

_mod_client: "Qbrix | None" = None
_lock = threading.Lock()


def _load_client() -> "Qbrix":
    global _mod_client
    if _mod_client is None:
        with _lock:
            if _mod_client is None:
                from qbrix._client import Qbrix

                _mod_client = Qbrix()
    return _mod_client


def _reset_client() -> None:
    """Reset the module-level default client. Useful in tests."""
    global _mod_client
    with _lock:
        _mod_client = None
