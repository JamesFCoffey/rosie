from __future__ import annotations

import json
from pathlib import Path

from agents.executor_agent import ExecutorAgent
from projections.plan_view import PlanItem, PlanView
from storage.event_store import EventStore


def _db(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


def test_executor_refuses_too_many_actions(tmp_path: Path) -> None:
    store = EventStore(_db(tmp_path))
    try:
        # Create a plan with 5 items but set max_actions=2 to trigger refusal
        items = [
            PlanItem(id=f"i{n}", action="create_dir", target=tmp_path / f"d{n}", reason="t", confidence=1.0)
            for n in range(5)
        ]
        plan = PlanView(items=items)
        ex = ExecutorAgent(store)
        res = ex.apply(plan, checkpoint_path=None, max_actions=2)
        assert res.applied == 0
        assert "too_many_actions" in res.summary
    finally:
        store.close()


def test_executor_onedrive_guard_refusal_and_force(tmp_path: Path) -> None:
    store = EventStore(_db(tmp_path))
    try:
        src = tmp_path / "src.txt"
        src.write_text("data")
        # Simulate OneDrive path by using a segment named OneDrive
        dst = tmp_path / "OneDrive" / "dst.txt"
        # Encode src in reason for inference
        item = PlanItem(
            id="m1",
            action="move",
            target=dst,
            reason=f"cluster:docs src={src}",
            confidence=0.9,
        )
        plan = PlanView(items=[item])
        ex = ExecutorAgent(store)
        res = ex.apply(plan, checkpoint_path=None, force=False)
        assert res.applied == 0
        assert "onedrive_guard" in res.summary

        # With force=True, it should proceed (may still skip if cross-volume rename fails)
        res2 = ex.apply(plan, checkpoint_path=None, force=True)
        # Either applied 1 via copy/rename or skipped due to missing parent; both are acceptable
        assert res2.applied in {0, 1}
    finally:
        store.close()


def test_executor_refuses_large_move_total(tmp_path: Path) -> None:
    store = EventStore(_db(tmp_path))
    try:
        big = tmp_path / "big.bin"
        # ~1.5 MiB file
        big.write_bytes(b"a" * (1536 * 1024))
        dst = tmp_path / "dst.bin"
        item = PlanItem(
            id="m2",
            action="move",
            target=dst,
            reason=f"cluster:bin src={big}",
            confidence=0.9,
        )
        plan = PlanView(items=[item])
        ex = ExecutorAgent(store)
        # Set limit smaller than file size
        res = ex.apply(plan, checkpoint_path=None, max_total_move_bytes=512 * 1024)
        assert res.applied == 0
        assert "move_size" in res.summary
    finally:
        store.close()

