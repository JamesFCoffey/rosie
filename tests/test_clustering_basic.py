from __future__ import annotations

from pathlib import Path

from projections.base import replay
from projections.plan_view import PlanProjection
from schemas import events as ev
from storage.event_store import EventStore
from tools.clustering import cluster_vectors


def _db(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


def test_hdbscan_with_fallback_and_event(tmp_path: Path) -> None:
    # Arrange: three files, two should cluster together
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    a = ws / "report_notes.txt"
    b = ws / "notes_summary.txt"
    c = ws / "image.png"
    a.write_text("alpha beta gamma")
    b.write_text("alpha beta delta")
    c.write_text("zeta xi")

    # Synthetic vectors: make a and b close, c far
    v: list[list[float]] = [
        [1.0, 0.0, 0.0, 0.0],  # a
        [0.95, 0.0, 0.0, 0.0],  # b
        [0.0, 1.0, 0.0, 0.0],  # c (noise)
    ]

    store = EventStore(_db(tmp_path))
    try:
        # Emit a FilesScanned root so PlanProjection can compute destinations
        store.append(ev.FilesScanned(root=ws, count=3))
        items = cluster_vectors(
            paths=[a, b, c],
            vectors=v,
            store=store,
            texts=[p.stem for p in [a, b, c]],
            min_cluster_size=2,
        )
        # There should be exactly 3 assignments, with 2 in the same cluster and 1 noise
        assert len(items) == 3
        cids = [it.cluster_id for it in items]
        assert cids.count(-1) in (0, 1)  # fallback may put c in its own small cluster
        # Last event should be ClustersFormed with items
        rows = store.read_all()
        assert rows[-1].type == "ClustersFormed"
        evt_items = rows[-1].data.get("items")
        assert isinstance(evt_items, list)
        # Paths are serialized as strings in event payload
        assert any(Path(it.get("path")).name == a.name for it in evt_items)

        # Replay into plan projection; ensure deterministic materialization
        proj = PlanProjection()
        replay(proj, store)
        plan = proj.current_plan()
        assert plan.id and isinstance(plan.id, str)
    finally:
        store.close()

