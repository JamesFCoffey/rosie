from __future__ import annotations

from pathlib import Path

from projections.base import replay
from projections.plan_view import PlanProjection
from schemas import events as ev
from storage.event_store import EventStore


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


def _append_sample_events(store: EventStore, tmp_path: Path) -> None:
    # A small, deterministic sequence mixing event types.
    store.append(ev.FilesScanned(root=tmp_path, count=2))
    store.append(ev.RuleMatched(path=tmp_path / "a.txt", rule_id="R1"))
    store.append(ev.RuleMatched(path=tmp_path / "b.log", rule_id="R2"))
    store.append(ev.EmbeddingsComputed(count=0))
    store.append(ev.ClustersFormed(count=0))


def test_same_events_same_plan_hash(tmp_path: Path) -> None:
    store = EventStore(_db_path(tmp_path))
    try:
        _append_sample_events(store, tmp_path)

        proj1 = PlanProjection()
        replay(proj1, store)
        plan1 = proj1.current_plan()

        # Rebuild from scratch and assert same id
        proj2 = PlanProjection()
        replay(proj2, store)
        plan2 = proj2.current_plan()

        assert plan1.id == plan2.id
        # Items must be equal when compared as dicts
        assert [i.model_dump(mode="json") for i in plan1.items] == [
            i.model_dump(mode="json") for i in plan2.items
        ]
    finally:
        store.close()


def test_correction_bumps_plan_hash(tmp_path: Path) -> None:
    store = EventStore(_db_path(tmp_path))
    try:
        _append_sample_events(store, tmp_path)

        proj = PlanProjection()
        replay(proj, store)
        plan_before = proj.current_plan()

        # Add a correction and re-materialize; hash should change deterministically.
        store.append(ev.CorrectionAdded(plan_id=plan_before.id, note="rename a.txt"))

        proj_after = PlanProjection()
        replay(proj_after, store)
        plan_after = proj_after.current_plan()

        assert plan_before.id != plan_after.id

        # Replay again to ensure determinism of the new hash
        proj_after2 = PlanProjection()
        replay(proj_after2, store)
        assert plan_after.id == proj_after2.current_plan().id
    finally:
        store.close()
