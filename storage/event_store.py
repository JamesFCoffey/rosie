"""SQLite-backed append-only event store.

Provides durable, append-only persistence for domain events with integrity checks.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence

try:  # Prefer blake3 if available
    from blake3 import blake3 as _blake3

    def _hash_bytes(data: bytes) -> str:
        return _blake3(data).hexdigest()

    HASH_ALGO = "blake3"
except Exception:  # Fallback to sha256 if blake3 is unavailable
    import hashlib

    def _hash_bytes(data: bytes) -> str:  # type: ignore[no-redef]
        return hashlib.sha256(data).hexdigest()

    HASH_ALGO = "sha256"


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EventRecord:
    """Stored event row."""

    id: int
    ts: int
    type: str
    data: Mapping[str, Any]
    checksum: str
    schema_ver: int


class EventStore:
    """SQLite append-only store.

    Creates the `events` table if it does not exist. Uses WAL for durability.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        if self._db_path.parent and not self._db_path.parent.exists():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute(
            (
                "CREATE TABLE IF NOT EXISTS events (\n"
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                "  ts INTEGER NOT NULL,\n"
                "  type TEXT NOT NULL,\n"
                "  data BLOB NOT NULL,\n"
                "  checksum TEXT NOT NULL,\n"
                "  schema_ver INTEGER NOT NULL\n"
                ")"
            )
        )
        self._conn.commit()

    def _compute_checksum(self, event_type: str, data_bytes: bytes) -> str:
        return _hash_bytes(event_type.encode("utf-8") + data_bytes)

    def _event_to_type_and_bytes(self, event: Any) -> tuple[str, bytes]:
        # Prefer Pydantic BaseModel-like objects with model_dump
        if hasattr(event, "model_dump") and callable(getattr(event, "model_dump")):
            # Prefer JSON-friendly dump (Pydantic v2)
            try:
                payload = event.model_dump(mode="json")  # type: ignore[call-arg]
            except TypeError:
                payload = event.model_dump()  # type: ignore[no-any-return]
            event_type = event.__class__.__name__
        elif isinstance(event, Mapping) and "type" in event and "data" in event:
            event_type = str(event["type"])  # type: ignore[index]
            payload = event["data"]  # type: ignore[index]
        else:
            # Fallback: treat object as a mapping and infer type from class name
            if isinstance(event, Mapping):
                payload = dict(event)  # shallow copy
            else:
                # Last resort: serialize __dict__
                payload = getattr(event, "__dict__", {})
            event_type = event.__class__.__name__
        data_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return event_type, data_bytes

    def append(self, event: Any) -> int:
        """Append a single event.

        Args:
            event: Pydantic model instance (preferred) or mapping-like object.

        Returns:
            Inserted row id.
        """
        event_type, data_bytes = self._event_to_type_and_bytes(event)
        ts = int(time.time() * 1000)
        checksum = self._compute_checksum(event_type, data_bytes)
        cur = self._conn.execute(
            "INSERT INTO events (ts, type, data, checksum, schema_ver) VALUES (?, ?, ?, ?, ?)",
            (ts, event_type, data_bytes, checksum, SCHEMA_VERSION),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def read_since(self, last_id: int) -> List[EventRecord]:
        """Read events with id greater than the provided value."""
        cur = self._conn.execute(
            "SELECT id, ts, type, data, checksum, schema_ver FROM events WHERE id > ? ORDER BY id ASC",
            (last_id,),
        )
        rows = cur.fetchall()
        out: List[EventRecord] = []
        for r in rows:
            data_dict = json.loads(r[3])
            out.append(
                EventRecord(
                    id=int(r[0]),
                    ts=int(r[1]),
                    type=str(r[2]),
                    data=data_dict,
                    checksum=str(r[4]),
                    schema_ver=int(r[5]),
                )
            )
        return out

    def read_all(self) -> List[EventRecord]:
        """Read all events in id order."""
        return self.read_since(0)

    def last_id(self) -> int:
        """Return the last inserted event id, or 0 if empty."""
        cur = self._conn.execute("SELECT COALESCE(MAX(id), 0) FROM events")
        (val,) = cur.fetchone()
        return int(val)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        try:
            self._conn.close()
        except Exception:
            pass


def compute_checksum(event_type: str, payload: dict) -> str:
    """Compute checksum for tests and utilities.

    Args:
        event_type: Name of the event type/class.
        payload: JSON-serializable mapping.

    Returns:
        Hex digest string using preferred hash (blake3 if available).
    """
    data_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _hash_bytes(event_type.encode("utf-8") + data_bytes)
