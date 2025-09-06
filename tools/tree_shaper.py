"""Tree shaping (stub)."""

from __future__ import annotations

from typing import Iterable, List, TypeVar

T = TypeVar("T")


def prune(items: Iterable[T], *, max_depth: int | None, max_children: int | None) -> List[T]:
    # Stub: return first N items if max_children set; depth unused.
    out = list(items)
    if max_children is not None:
        out = out[: max(0, max_children)]
    return out

