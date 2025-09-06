"""File index projection.

Maintains a simple in-memory index of file metadata keyed by path.
This projection is fed by events; since current events do not provide
size/mtime/hash values, those fields are optional and can be populated by
future events. The projection itself remains deterministic by only using
data present in events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from storage.event_store import EventRecord


@dataclass
class FileIndex:
    """Materialized view for file metadata."""

    entries: Dict[Path, dict] = field(default_factory=dict)

    def apply(self, event: EventRecord) -> None:
        """Apply a single event to update the index.

        Recognized events (based on current schemas):
        - RuleMatched: introduces a path into the index if not present.

        Args:
            event: EventRecord from the event store.
        """
        et = event.type
        data = event.data
        if et == "RuleMatched":
            # Minimal metadata; future events can enrich these fields.
            p = Path(data["path"])  # serialized by pydantic as string
            self.entries.setdefault(
                p,
                {
                    "path": p,
                    "size": cast(Optional[int], None),
                    "mtime": cast(Optional[float], None),
                    "hash_hint": cast(Optional[str], None),
                },
            )


def cast(type_, value):  # small internal helper to avoid importing typing.cast
    return value
