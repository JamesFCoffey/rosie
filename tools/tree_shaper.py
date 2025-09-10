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
    """Make a Windows-safe folder label.

    - Replace reserved characters: <>:"/\|?*
    - Strip trailing spaces and dots
    - Avoid reserved device names (CON, PRN, AUX, NUL, COM1..9, LPT1..9)
    - Fallback to "cluster" when empty
    """
    bad = '<>:"/\\|?*'
    cleaned = "".join((c if c not in bad else "_") for c in label)
    cleaned = cleaned.strip().rstrip(" .")
    if not cleaned:
        cleaned = "cluster"
    # Avoid reserved device names (case-insensitive)
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if cleaned.upper() in reserved:
        cleaned = f"_{cleaned}"
    return cleaned


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
    # Base directory: depth>=1 allows creating the label directory under root
    base = root if depth <= 0 else root / safe

    m = list(members)
    # If no constraints, keep all directly under base (or root)
    if not max_children or int(max_children) <= 0:
        return ([base] if depth > 0 else [base]), [(p, base / p.name) for p in m]

    per = max(1, int(max_children))

    # Helper: build a bounded fan-out tree deterministically.
    # levels_left counts how many directory levels are available below `cur`.
    def capacity(levels_left: int) -> int:
        # Each level multiplies capacity by `per`; at leaf we can keep up to `per` files.
        if levels_left <= 0:
            return per
        cap = per
        for _ in range(levels_left):
            cap *= per
        return cap

    dirs: list[Path] = [base] if depth > 0 else [base]
    moves: list[tuple[Path, Path]] = []

    # Additional directory levels allowed below `base` (not counting files)
    # Example: depth=2 => one level below base (e.g., part_001)
    levels_left = max(0, depth - 1)

    def place(cur: Path, items: list[Path], levels_left: int, part_prefix: str = "") -> None:
        nonlocal dirs, moves
        if not items:
            return
        if levels_left <= 0:
            # No more subdirs allowed; place up to `per` files directly under cur
            keep = items[:per]
            moves.extend((p, cur / p.name) for p in keep)
            return
        # We may create up to `per` subdirectories under `cur`.
        sub_cap = capacity(levels_left - 1)  # how many files a single subtree can hold
        # Determine number of required subdirs but cap at `per`
        needed = (len(items) + sub_cap - 1) // sub_cap
        count = min(per, max(1, needed))
        # Split into contiguous chunks of size <= sub_cap
        idx = 0
        for i in range(1, count + 1):
            chunk = items[idx : idx + sub_cap]
            if not chunk:
                break
            sub = cur / f"{part_prefix}part_{i:03d}"
            dirs.append(sub)
            place(sub, chunk, levels_left - 1)
            idx += len(chunk)

    # If depth <= 1, we cannot create subdirs; place/prune directly under base
    if levels_left == 0:
        keep = m[:per]
        moves.extend((p, base / p.name) for p in keep)
        return dirs, moves

    # Else, build a bounded fan-out below base
    place(base, m, levels_left)
    return dirs, moves
