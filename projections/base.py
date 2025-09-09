"""Projection helpers.

Provides a simple replay loop to build materialized views from events.
"""

from __future__ import annotations

from typing import Protocol

from storage.event_store import EventRecord, EventStore


class AppliesEvent(Protocol):
    def apply(self, event: EventRecord) -> None:  # pragma: no cover - Protocol definition only
        ...


def replay(projection: AppliesEvent, store: EventStore, since_id: int = 0) -> int:
    """Replay events from the store into the projection.

    Args:
        projection: Object exposing an ``apply(event)`` method.
        store: EventStore instance to read from.
        since_id: Starting id (exclusive); pass last applied id.

    Returns:
        The last processed event id (0 if none processed).
    """
    last = since_id
    for ev in store.read_since(since_id):
        projection.apply(ev)
        last = ev.id
    return last
