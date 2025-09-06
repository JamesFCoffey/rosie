"""Embedding cache projection (stub)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class EmbeddingCache:
    # key: (content_hash, mtime) -> vector
    entries: Dict[Tuple[str, float], list[float]]

