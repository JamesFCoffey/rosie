"""Async file scanner.

Provides an asyncio-friendly directory walker that emits ``FilesScanned``
events in batches with basic file metadata. The scanner is conservative and
Windows-aware:

- Does not follow reparse points (junctions/symlinks)
- Skips common deny-listed directories (e.g., ``.git``, ``node_modules``)
- Collects ``size`` and ``mtime`` for files (directories reported as metadata-only)

The scanner itself is side-effect free aside from event emission; callers may
use it to populate projections deterministically.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from os_win.reparse_points import is_reparse_point
from schemas import events as ev
from storage.event_store import EventStore


DENY_DIR_NAMES: set[str] = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "$RECYCLE.BIN",
    "System Volume Information",
}


@dataclass(frozen=True)
class ScannedItem:
    """Lightweight metadata for a scanned filesystem entry."""

    path: Path
    size: int
    mtime: float
    is_dir: bool


def _matches_any(p: Path, patterns: Sequence[str]) -> bool:
    name = p.name
    for glob in patterns:
        if p.match(glob) or name == glob:
            return True
    return False


_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_SYSTEM = 0x4


def _is_hidden_or_system(p: Path) -> bool:
    """Return True if path is hidden or system.

    On Windows, checks file attributes via ``os.lstat``. On non-Windows,
    treats names starting with a dot as hidden. Errors are treated as not hidden
    to avoid over-filtering due to transient failures.
    """
    try:
        import os as _os

        st = _os.lstat(p)
        attrs = getattr(st, "st_file_attributes", None)
        if attrs is not None:
            return bool(attrs & (_FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM))
    except Exception:
        # Fall through to name-based heuristic
        pass
    name = p.name
    return name.startswith(".")


def _iter_entries(
    *,
    root: Path,
    include: Sequence[str],
    exclude: Sequence[str],
    deny_dirs: set[str],
    exclude_hidden: bool = True,
) -> Iterable[ScannedItem]:
    """Synchronous walker yielding ``ScannedItem`` entries.

    Skips reparse points and deny-listed directories. Does not follow links.
    """
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dpath = Path(dirpath)

        # Prune deny-listed directories in-place (case-sensitive match by name)
        dirnames[:] = [d for d in dirnames if d not in deny_dirs]

        # Skip reparse points without descending into them
        # Filter in-place to prevent traversal into reparse points
        safe_dirnames = []
        for d in dirnames:
            child = dpath / d
            try:
                if is_reparse_point(child):
                    continue
            except Exception:
                # Be conservative: if detection fails, skip
                continue
            safe_dirnames.append(d)
        dirnames[:] = safe_dirnames

        # Yield directory entry metadata (size 0), subject to include/exclude
        if (not include or _matches_any(dpath, include)) and not _matches_any(dpath, exclude):
            try:
                st = os.lstat(dpath)
            except Exception:
                st = None
            # Skip hidden/system directories by default
            if not (exclude_hidden and _is_hidden_or_system(dpath)):
                yield ScannedItem(path=dpath, size=0, mtime=(st.st_mtime if st else 0.0), is_dir=True)

        # Yield files in this directory
        for fname in filenames:
            fp = dpath / fname
            if include and not _matches_any(fp, include):
                continue
            if exclude and _matches_any(fp, exclude):
                continue
            try:
                # lstat avoids following symlinks; we'll skip if it's a reparse point
                if is_reparse_point(fp):
                    continue
                st = os.lstat(fp)
            except Exception:
                continue
            # Skip hidden/system files by default
            if exclude_hidden and _is_hidden_or_system(fp):
                continue
            yield ScannedItem(path=fp, size=int(getattr(st, "st_size", 0)), mtime=float(st.st_mtime), is_dir=False)


async def scan_and_emit(
    *,
    root: Path,
    store: EventStore,
    include: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
    deny_dirs: Optional[set[str]] = None,
    exclude_hidden: bool = True,
    batch_size: int = 512,
) -> int:
    """Scan ``root`` and append ``FilesScanned`` events in batches.

    Args:
        root: Root directory to scan.
        store: Event store to append ``FilesScanned`` events to.
        include: Optional include globs; if provided, entries must match at least one.
        exclude: Optional exclude globs; if provided, entries matching any are skipped.
        deny_dirs: Directory names to prune entirely from traversal.
        batch_size: Max number of entries per emitted event.

    Returns:
        Total count of scanned entries emitted.
    """
    inc = tuple(include or [])
    exc = tuple(exclude or [])
    denies = set(deny_dirs or DENY_DIR_NAMES)

    total = 0
    batch: list[dict] = []

    def _flush() -> None:
        nonlocal batch, total
        if not batch:
            return
        try:
            store.append(
                ev.FilesScanned(
                    root=root,
                    count=len(batch),
                    batch=[
                        {
                            "path": str(it["path"]),
                            "size": int(it["size"]),
                            "mtime": float(it["mtime"]),
                            "is_dir": bool(it["is_dir"]),
                        }
                        for it in batch
                    ],
                )
            )
        finally:
            total += len(batch)
            batch = []

    # Walk in a thread to avoid blocking the event loop on large trees
    loop = asyncio.get_running_loop()

    def _produce() -> None:
        for item in _iter_entries(
            root=root, include=inc, exclude=exc, deny_dirs=denies, exclude_hidden=exclude_hidden
        ):
            batch.append({
                "path": item.path,
                "size": item.size,
                "mtime": item.mtime,
                "is_dir": item.is_dir,
            })
            if len(batch) >= batch_size:
                _flush()

    await loop.run_in_executor(None, _produce)
    _flush()
    return total


def scan_paths(*, root: Path, include: List[str], exclude: List[str]) -> Iterable[Path]:
    """Compatibility helper used by orchestrator stub.

    Yields files and directories under root honoring basic include/exclude globs.
    """
    yield from (
        it.path
        for it in _iter_entries(
            root=root, include=include, exclude=exclude, deny_dirs=DENY_DIR_NAMES, exclude_hidden=True
        )
    )
