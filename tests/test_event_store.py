from __future__ import annotations

from pathlib import Path
from typing import Any

from projections import base as proj_base
from schemas import events as ev
from storage.event_store import EventStore, compute_checksum


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


def test_append_and_read_all(tmp_path: Path) -> None:
    store = EventStore(_db_path(tmp_path))
    try:
        e1 = ev.FilesScanned(root=tmp_path, count=3)
        e2 = ev.RuleMatched(path=tmp_path / "a.txt", rule_id="R1")
        id1 = store.append(e1)
        id2 = store.append(e2)

        rows = store.read_all()
        assert [r.id for r in rows] == [id1, id2]
        assert rows[0].type == "FilesScanned"
        assert rows[1].type == "RuleMatched"
        assert rows[0].data["count"] == 3
        assert rows[1].data["rule_id"] == "R1"
        assert rows[0].schema_ver == 1
        assert isinstance(rows[0].ts, int) and rows[0].ts > 0
    finally:
        store.close()


def test_read_since_and_last_id(tmp_path: Path) -> None:
    store = EventStore(_db_path(tmp_path))
    try:
        e1 = ev.FilesScanned(root=tmp_path, count=1)
        e2 = ev.FilesScanned(root=tmp_path, count=2)
        id1 = store.append(e1)
        id2 = store.append(e2)

        assert store.last_id() == id2
        assert [r.id for r in store.read_since(0)] == [id1, id2]
        assert [r.id for r in store.read_since(id1)] == [id2]
        assert store.read_since(id2) == []
    finally:
        store.close()


def test_checksum_blake3(tmp_path: Path) -> None:
    store = EventStore(_db_path(tmp_path))
    try:
        event = ev.EmbeddingsComputed(count=5)
        store.append(event)
        (row,) = store.read_all()
        # Recompute checksum deterministically using the same algorithm
        expected = compute_checksum(row.type, dict(row.data))  # uses blake3 if available
        assert row.checksum == expected
    finally:
        store.close()


def test_projection_replay_helper(tmp_path: Path) -> None:
    class Collector:
        def __init__(self) -> None:
            self.seen: list[str] = []

        def apply(self, event: Any) -> None:  # use Protocol signature
            self.seen.append(f"{event.id}:{event.type}")

    store = EventStore(_db_path(tmp_path))
    try:
        ids = [store.append(ev.ClustersFormed(count=i)) for i in range(3)]
        c = Collector()
        last = proj_base.replay(c, store, since_id=0)
        assert last == ids[-1]
        assert c.seen == [f"{i}:ClustersFormed" for i in ids]

        # Replay from last id should yield nothing new
        last2 = proj_base.replay(c, store, since_id=last)
        assert last2 == last
        assert c.seen == [f"{i}:ClustersFormed" for i in ids]
    finally:
        store.close()
