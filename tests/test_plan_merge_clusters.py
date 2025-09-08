from __future__ import annotations

from pathlib import Path

from projections.base import replay
from projections.plan_view import PlanProjection
from schemas import events as ev
from storage.event_store import EventStore


def _db(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


def test_plan_merges_cluster_create_and_move(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    f1 = ws / "doc1.txt"
    f2 = ws / "doc2.txt"
    f3 = ws / "other.bin"
    for p in (f1, f2, f3):
        p.write_text("x")

    store = EventStore(_db(tmp_path))
    try:
        # Seed root and a clusters event (two docs in cluster 0 labeled 'docs'; f3 is noise)
        store.append(ev.FilesScanned(root=ws, count=3))
        items = [
            ev.ClusterAssignment(path=f1, cluster_id=0, confidence=0.9, label="docs"),
            ev.ClusterAssignment(path=f2, cluster_id=0, confidence=0.8, label="docs"),
            ev.ClusterAssignment(path=f3, cluster_id=-1, confidence=0.0, label=None),
        ]
        store.append(ev.ClustersFormed(count=1, items=items))

        proj = PlanProjection()
        replay(proj, store)
        plan = proj.current_plan()
        dumped = [i.model_dump(mode="json") for i in plan.items]

        # Expect a create_dir for ws/docs and two move actions into that folder
        create_targets = [Path(d["target"]) for d in dumped if d["action"] == "create_dir"]
        assert (ws / "docs") in set(create_targets)

        move_targets = [Path(d["target"]) for d in dumped if d["action"] == "move"]
        assert (ws / "docs" / f1.name) in set(move_targets)
        assert (ws / "docs" / f2.name) in set(move_targets)
        # Noise item should not produce a move
        assert (ws / "docs" / f3.name) not in set(move_targets)
    finally:
        store.close()

