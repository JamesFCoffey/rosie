"""Embedding cache projection.

Maps content-hash keys to embedding vectors. The vectors are stored as
JSON-serializable Python lists (can be serialized to BLOB/JSON in a DB
adapter if needed). Current events do not carry embedding payloads; this
projection exposes imperative methods for tools to populate the cache,
while remaining replay-friendly (no side effects during apply).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from storage.event_store import EventRecord


@dataclass
class EmbeddingCache:
    """Materialized embedding cache.

    Keys are ``(content_hash, mtime)`` to differentiate same content across
    edits if desired by callers. Use ``mtime=0.0`` for pure content-hash keys.
    """

    entries: dict[tuple[str, float], list[float]] = field(default_factory=dict)

    def apply(self, event: EventRecord) -> None:
        """Apply events that may relate to embeddings.

        Current schemas only expose a count in ``EmbeddingsComputed`` which
        does not alter the cache, so this is a no-op to keep deterministic
        replay semantics.
        """
        # No-op for now; placeholder for future embedding events.
        _ = event

    def put(self, *, content_hash: str, mtime: float, vector: Iterable[float]) -> None:
        """Insert/replace an embedding vector.

        Args:
            content_hash: Deterministic content hash for the item.
            mtime: Optional mtime discriminator (use 0.0 if not needed).
            vector: Embedding values.
        """
        self.entries[(content_hash, mtime)] = list(vector)

    def get(self, *, content_hash: str, mtime: float = 0.0) -> list[float] | None:
        """Retrieve an embedding vector by key.

        Args:
            content_hash: Key hash.
            mtime: Matching mtime.

        Returns:
            The vector if present, else None.
        """
        return self.entries.get((content_hash, mtime))
