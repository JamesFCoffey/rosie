"""File index projection.

Maintains a materialized index of file metadata keyed by path and aggregates
folder sizes for quick "largest folders" queries. This projection consumes
``FilesScanned`` events that may include optional batch payloads with file
metadata and remains deterministic by only using event data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from storage.event_store import EventRecord


@dataclass
class FileMeta:
    path: Path
    size: int
    mtime: float
    is_dir: bool


@dataclass
class FileIndex:
    """Materialized view for file metadata and folder aggregates."""

    root: Optional[Path] = None
    entries: Dict[Path, FileMeta] = field(default_factory=dict)
    folder_sizes: Dict[Path, int] = field(default_factory=dict)

    def apply(self, event: EventRecord) -> None:
        """Apply a single event to update the index.

        Recognized events:
        - FilesScanned: optionally carries a ``batch`` of items with metadata.
        - RuleMatched: introduces a path (legacy compatibility; no size info).
        """
        et = event.type
        data = event.data
        if et == "FilesScanned":
            if "root" in data and data["root"]:
                try:
                    self.root = Path(data["root"])  # Path serialized to str
                except Exception:
                    self.root = None
            batch = data.get("batch") or []
            for item in batch:
                try:
                    p = Path(item["path"])  # serialized by pydantic as string
                    size = int(item.get("size", 0))
                    mtime = float(item.get("mtime", 0.0))
                    is_dir = bool(item.get("is_dir", False))
                except Exception:
                    continue

                # Insert/update entry
                prev = self.entries.get(p)
                prev_size = prev.size if prev is not None else 0
                self.entries[p] = FileMeta(path=p, size=size, mtime=mtime, is_dir=is_dir)

                # Update folder aggregates only for files; directories carry size 0
                if not is_dir:
                    delta = size - prev_size
                    self._bump_folder_sizes(p.parent, delta)

        elif et == "RuleMatched":
            p = Path(data["path"])  # serialized by pydantic as string
            if p not in self.entries:
                self.entries[p] = FileMeta(path=p, size=cast(Optional[int], 0), mtime=cast(Optional[float], 0.0), is_dir=p.is_dir())

    def _bump_folder_sizes(self, start: Path, delta: int) -> None:
        """Increment folder sizes by ``delta`` up to (and including) root.

        If ``root`` is unknown, walk up to the filesystem root of ``start``.
        """
        cur = start
        while True:
            self.folder_sizes[cur] = self.folder_sizes.get(cur, 0) + delta
            if self.root is not None:
                if cur == self.root or self.root in cur.parents:
                    # Stop once we've recorded at or above the scan root
                    if cur == self.root:
                        break
            # Termination at filesystem root
            if cur.parent == cur:
                break
            cur = cur.parent

    def largest_folders(self, *, limit: int = 20) -> List[Tuple[Path, int]]:
        """Return top-N folders by aggregated size.

        Args:
            limit: Maximum number of results.

        Returns:
            A list of ``(folder_path, total_size_bytes)`` sorted descending.
        """
        items = sorted(self.folder_sizes.items(), key=lambda kv: kv[1], reverse=True)
        return items[: max(0, limit)]


def cast(type_, value):  # small internal helper to avoid importing typing.cast
    return value
