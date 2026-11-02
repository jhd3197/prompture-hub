"""Process-local ledger of in-flight call cost reservations.

A usage row is only written when a call finishes, so without this a burst of
concurrent (or long streaming) calls all see the same headroom and overshoot
the spend cap, and in-flight calls don't count toward the rate limit. Each
admitted call holds a :class:`Reservation` until it settles.

The ledger lives in this process's memory: it assumes a single hub process
(the Docker image runs one uvicorn). With several workers each would only see
its own reservations. Check-and-reserve is atomic under :data:`lock`, which
callers hold while reading spend so the read and the reservation can't be
interleaved with another request.
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Any

#: Held by :func:`prompture_hub.quotas.reserve` around check + add. Re-entrant.
lock = threading.RLock()
#: Monotonic clock; tests replace it to age reservations.
clock = time.monotonic

_ids = itertools.count(1)
_active: dict[int, dict[int, Reservation]] = {}


@dataclass
class Reservation:
    """Estimated cost held for one in-flight call; release it exactly when the call settles."""

    key_id: int
    amount: float
    expires: float
    #: Prices are known and non-zero, so a zero-cost result is suspicious.
    priced: bool = False
    #: The model has no known prices (HUB_UNKNOWN_PRICING=warn); nothing is reserved.
    unknown_pricing: bool = False
    rates: Any = None
    id: int = field(default_factory=lambda: next(_ids))
    released: bool = False

    def release(self) -> None:
        """Drop the hold. Idempotent, so every settle/error/disconnect path may call it."""
        with lock:
            if self.released:
                return
            self.released = True
            _active.get(self.key_id, {}).pop(self.id, None)


def add(key_id: int, amount: float, ttl: float, **fields: Any) -> Reservation:
    with lock:
        res = Reservation(key_id=key_id, amount=amount, expires=clock() + ttl, **fields)
        _active.setdefault(key_id, {})[res.id] = res
        return res


def _live(key_id: int) -> list[Reservation]:
    with lock:
        held = _active.get(key_id, {})
        now = clock()
        for res in [r for r in held.values() if r.expires <= now]:
            res.release()
        return list(held.values())


def reserved_usd(key_id: int) -> float:
    return sum(r.amount for r in _live(key_id))


def in_flight(key_id: int) -> int:
    return len(_live(key_id))


def reset() -> None:
    with lock:
        _active.clear()
