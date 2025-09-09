"""Conflict resolver (stub)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def resolve(items: Iterable[T]) -> list[T]:
    # Stub: return as-is
    return list(items)
