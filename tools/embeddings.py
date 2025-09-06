"""Embeddings loader/cache (stub)."""

from __future__ import annotations

from typing import Iterable, List, Sequence


def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    """Return zero-vectors as placeholder embeddings."""
    return [[0.0] * 8 for _ in texts]

