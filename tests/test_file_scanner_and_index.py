from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from projections.base import replay
from projections.file_index import FileIndex
from storage.event_store import EventStore
from tools import file_scanner


def _db_path(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


def _write(p: Path, size: int) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x" * size)


def test_scanner_emits_batches_and_index_aggregates(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    # Create a small tree; include a deny-listed dir which should be skipped
    _write(ws / "a" / "x1.dat", 10)
    _write(ws / "a" / "b" / "y2.dat", 20)
    _write(ws / "node_modules" / "nm.dat", 1000)

    # Add a symlink that would create a cycle if followed
    link = ws / "link_to_a"
    target = ws / "a"
    if sys.platform != "win32":
        try:
            os.symlink(target, link, target_is_directory=True)
        except Exception:
            pass

    store = EventStore(_db_path(tmp_path))
    try:
        # Emit scan in small batches to force multiple events
        total = asyncio.run(file_scanner.scan_and_emit(root=ws, store=store, batch_size=2))
        rows = store.read_all()
        # Only FilesScanned events are expected here
        assert all(r.type == "FilesScanned" for r in rows)
        assert sum(r.data.get("count", 0) for r in rows) == total

        # Build index and compute largest folders (recursive sums)
        idx = FileIndex()
        replay(idx, store)
        top = dict(idx.largest_folders(limit=10))

        # node_modules should be excluded; sizes should aggregate
        assert top.get(ws / "a") == 30  # 10 + 20
        assert top.get(ws / "a" / "b") == 20
        # root folder should be at least the sum of non-deny-listed files
        assert top.get(ws) in {30, 30 + 0}  # exact value depends on where root counting stops
    finally:
        store.close()
