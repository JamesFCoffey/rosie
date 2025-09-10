from __future__ import annotations

from pathlib import Path

from projections.base import replay
from projections.plan_view import PlanProjection
from schemas import events as ev
from storage.event_store import EventStore


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "events_limits.db"


def _append_cluster_events(store: EventStore, tmp_path: Path, n: int = 12) -> None:
    store.append(ev.FilesScanned(root=tmp_path, count=n))
    items = [
        ev.ClusterAssignment(
            path=tmp_path / f"f{i}.txt", cluster_id=0, confidence=0.5, label="Group"
        )
        for i in range(n)
    ]
    store.append(ev.ClustersFormed(count=1, items=items))


def test_plan_hash_changes_with_limits(tmp_path: Path) -> None:
    store = EventStore(_db_path(tmp_path))
    try:
        _append_cluster_events(store, tmp_path, n=12)

        proj1 = PlanProjection(max_depth=2, max_children=3)
        replay(proj1, store)
        plan1 = proj1.current_plan()

        # Same limits => same id
        proj2 = PlanProjection(max_depth=2, max_children=3)
        replay(proj2, store)
        plan2 = proj2.current_plan()
        assert plan1.id == plan2.id

        # Changing a limit => different id
        proj3 = PlanProjection(max_depth=3, max_children=3)
        replay(proj3, store)
        plan3 = proj3.current_plan()
        assert plan1.id != plan3.id

        proj4 = PlanProjection(max_depth=2, max_children=4)
        replay(proj4, store)
        plan4 = proj4.current_plan()
        assert plan1.id != plan4.id
    finally:
        store.close()
