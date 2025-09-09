"""Tree shaping utilities for max-depth/max-children constraints.

Provides helpers to constrain proposed folder structures to a maximum depth
and number of children per directory. These functions are pure (no I/O) and
return destinations for move operations alongside directories to create.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


def prune(items: Iterable[T], *, max_depth: int | None, max_children: int | None) -> list[T]:
    """Prune a flat collection to respect ``max_children``.

    This is a minimal helper used in a few places where only a flat limit is
    relevant. ``max_depth`` is ignored for flat lists by design.
    """
    out = list(items)
    if max_children is not None:
        out = out[: max(0, int(max_children))]
    return out


def sanitize_label(label: str) -> str:
    """Make a folder-friendly label (basic Windows-safe filtering)."""
    bad = '<>:"/\\|?*'
    cleaned = "".join((c if c not in bad else "_") for c in label).strip()
    return cleaned or "cluster"


def shape_cluster_moves(
    *,
    root: Path,
    label: str,
    members: Sequence[Path],
    max_depth: int | None = 2,
    max_children: int | None = None,
) -> tuple[list[Path], list[tuple[Path, Path]]]:
    """Compute directories to create and move destinations for a cluster.

    Args:
        root: Scan root used as the base for proposed folders.
        label: Cluster label used for the top-level folder name.
        members: Files belonging to the cluster.
        max_depth: Maximum folder depth relative to ``root``.
        max_children: Maximum number of children per directory.

    Returns:
        A tuple ``(dirs_to_create, moves)`` where ``moves`` is a list of
        ``(src, dst)`` pairs.
    """
    safe = sanitize_label(label)
    # Determine base destination respecting max_depth
    depth = max(0, int(max_depth)) if max_depth is not None else 2
    if depth <= 0:
        base = root
    else:
        base = root / safe

    # If no child limit or small cluster, place all directly under base
    m = list(members)
    if not max_children or len(m) <= int(max_children) or depth <= 1:
        dirs = [base]
        moves = [(p, base / p.name) for p in m]
        return dirs, moves

    # Split into evenly sized parts under base to satisfy child limit
    per = max(1, int(max_children))
    dirs: list[Path] = [base]
    moves: list[tuple[Path, Path]] = []
    part = 1
    chunk: list[Path] = []
    for p in m:
        chunk.append(p)
        if len(chunk) == per:
            sub = base / f"part_{part:03d}"
            dirs.append(sub)
            moves.extend((q, sub / q.name) for q in chunk)
            chunk = []
            part += 1
    if chunk:
        sub = base / f"part_{part:03d}"
        dirs.append(sub)
        moves.extend((q, sub / q.name) for q in chunk)
    return dirs, moves
