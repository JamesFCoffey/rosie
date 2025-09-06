"""Append-only event store (stub).

This stub keeps events in-memory. The public API mirrors a future SQLite-backed store.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Protocol, Sequence


class Event(Protocol):
    """Structural type for events (Pydantic models will satisfy this)."""

    def model_dump(self) -> dict:  # type: ignore[override]
        ...


@dataclass
class StoredEvent:
    type: str
    payload: dict


class EventStore:
    """In-memory append-only store.

    Args:
        db_path: Target SQLite path (unused in stub; reserved for future persistence).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._events: List[StoredEvent] = []

    def append(self, event_type: str, event: Event) -> None:
        self._events.append(StoredEvent(type=event_type, payload=event.model_dump()))

    def iter(self) -> Iterable[StoredEvent]:
        return iter(self._events)

    def all(self) -> Sequence[StoredEvent]:
        return list(self._events)

