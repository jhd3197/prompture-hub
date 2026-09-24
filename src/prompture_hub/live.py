"""The hub's live event bus behind ``GET /v1/live``.

The bus itself lives in :mod:`prompture.companion.live`, shared with the local
companion server (``prompture companion``) so both stream identical events.
Metering publishes calls starting, producing their first token, changing
activity and finishing; events carry metadata only, never prompt or completion
text. The bus is per process: the hub is designed to run as one.
"""

from prompture.companion.live import (
    IN_FLIGHT_TTL,
    RING_SIZE,
    LiveBus,
    Subscriber,
    get_bus,
    new_request_id,
    sse_event,
    visible,
)

__all__ = [
    "IN_FLIGHT_TTL",
    "RING_SIZE",
    "LiveBus",
    "Subscriber",
    "get_bus",
    "new_request_id",
    "sse_event",
    "visible",
]
