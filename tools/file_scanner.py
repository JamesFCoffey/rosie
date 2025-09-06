"""Async file scanner (stub)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List


def scan_paths(*, root: Path, include: List[str], exclude: List[str]) -> Iterable[Path]:
    """Yield files and directories under root honoring basic include/exclude globs.

    This stub walks the tree and filters by name patterns.
    """
    root = root.resolve()
    for p in root.rglob("*"):
        name = p.name
        if include and not any(p.match(glob) or name == glob for glob in include):
            continue
        if exclude and any(p.match(glob) or name == glob for glob in exclude):
            continue
        yield p

