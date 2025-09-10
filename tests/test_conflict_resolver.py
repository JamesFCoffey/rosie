from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from projections.base import replay
from projections.plan_view import PlanProjection
from schemas import events as ev
from schemas.plan import PlanItemModel
from storage.event_store import EventStore
from tools import conflict_resolver as cr


def test_move_collision_suffix_deterministic(tmp_path: Path) -> None:
    # Two move items into the same target should be suffixed deterministically
    dst = tmp_path / "dst" / "file.txt"
    i1 = PlanItemModel(
        id="a",
        action="move",
        target=dst,
        reason=f"cluster:docs src={tmp_path / 'a.txt'}",
        confidence=0.9,
    )
    i2 = PlanItemModel(
        id="b",
        action="move",
        target=dst,
        reason=f"cluster:docs src={tmp_path / 'b.txt'}",
        confidence=0.8,
    )
    out = cr.resolve([i2, i1], root=tmp_path)  # reversed input to test ordering stability
    targets = [Path(o.target) for o in out if o.action == "move"]
    assert (tmp_path / "dst" / "file.txt") in set(targets)
    assert (tmp_path / "dst" / "file_2.txt") in set(targets)


def test_cross_volume_annotation(tmp_path: Path) -> None:
    @dataclass
    class Probe:
        def is_locked(self, path: Path) -> bool:
            return False

        def is_cross_volume(self, src: Path, dst: Path) -> bool:
            return True

    src = tmp_path / "s.txt"
    dst = tmp_path / "d.txt"
    item = PlanItemModel(
        id="m1",
        action="move",
        target=dst,
        reason=f"cluster:docs src={src}",
        confidence=0.9,
    )
    out = cr.resolve([item], root=tmp_path, probe=Probe())
    assert len(out) == 1
    assert out[0].target == dst
    assert "cross-volume" in out[0].reason


def test_onedrive_caution_and_confidence(tmp_path: Path) -> None:
    # Simulate OneDrive path via segment name
    src = tmp_path / "OneDrive" / "src.txt"
    dst = tmp_path / "dst.txt"
    item = PlanItemModel(
        id="m2",
        action="move",
        target=dst,
        reason=f"cluster:docs src={src}",
        confidence=0.95,
    )
    out = cr.resolve([item], root=tmp_path)
    assert len(out) == 1
    assert out[0].confidence <= 0.6
    assert out[0].reason.lower().startswith("caution: onedrive;")


def test_locked_paths_blocked_and_confidence(tmp_path: Path) -> None:
    locked_src = tmp_path / "locked_src.txt"
    locked_dst = tmp_path / "locked_dir"

    @dataclass
    class Probe:
        def is_locked(self, path: Path) -> bool:
            return path in {locked_src, locked_dst}

        def is_cross_volume(self, src: Path, dst: Path) -> bool:
            return False

    m = PlanItemModel(
        id="m3",
        action="move",
        target=tmp_path / "d.txt",
        reason=f"cluster:docs src={locked_src}",
        confidence=0.9,
    )
    c = PlanItemModel(
        id="c1",
        action="create_dir",
        target=locked_dst,
        reason="cluster:docs",
        confidence=0.9,
    )
    out = cr.resolve([m, c], root=tmp_path, probe=Probe())
    assert any(
        o.action == "move"
        and o.confidence <= 0.4
        and o.reason.lower().startswith("blocked: locked;")
        for o in out
    )
    assert any(
        o.action == "create_dir"
        and o.confidence <= 0.4
        and o.reason.lower().startswith("blocked: locked;")
        for o in out
    )


def test_replay_determinism_same_events_same_plan(tmp_path: Path) -> None:
    db = (tmp_path / "state").joinpath("events.db")
    ws = tmp_path / "ws"
    (ws / "a").mkdir(parents=True, exist_ok=True)
    (ws / "b").mkdir(parents=True, exist_ok=True)
    f1 = ws / "a" / "same.txt"
    f2 = ws / "b" / "same.txt"
    f1.write_text("1")
    f2.write_text("2")

    store = EventStore(db)
    try:
        store.append(ev.FilesScanned(root=ws, count=2))
        items = [
            ev.ClusterAssignment(path=f1, cluster_id=0, confidence=0.9, label="docs"),
            ev.ClusterAssignment(path=f2, cluster_id=0, confidence=0.8, label="docs"),
        ]
        store.append(ev.ClustersFormed(count=1, items=items))

        p1 = PlanProjection()
        replay(p1, store)
        plan1 = p1.current_plan()
        # Second replay into a fresh projection
        p2 = PlanProjection()
        replay(p2, store)
        plan2 = p2.current_plan()

        assert plan1.id == plan2.id
        # And targets are deterministically suffixed
        move_targets = [Path(i.target) for i in plan1.items if i.action == "move"]
        assert (ws / "docs" / "same.txt") in set(move_targets)
        assert (ws / "docs" / "same_2.txt") in set(move_targets)
    finally:
        store.close()
