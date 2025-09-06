from __future__ import annotations

from pathlib import Path

from schemas import events as ev


def _round_trip(model):
    data = model.to_json()
    cls = model.__class__
    again = cls.from_json(data)
    assert model.model_dump(mode="json") == again.model_dump(mode="json")
    assert getattr(again, "type", cls.__name__) == cls.__name__


def test_events_round_trip(tmp_path: Path) -> None:
    _round_trip(ev.FilesScanned(root=tmp_path, count=3))
    _round_trip(ev.RuleMatched(path=tmp_path / "a.txt", rule_id="R1"))
    _round_trip(ev.EmbeddingsComputed(count=5))
    _round_trip(ev.ClustersFormed(count=2))
    _round_trip(ev.PlanProposed(plan_id="p1", item_ids=["i1", "i2"]))
    _round_trip(ev.UserApproved(plan_id="p1", item_ids=["i1"]))
    _round_trip(ev.CorrectionAdded(plan_id="p1", note="fix name"))
    _round_trip(ev.PlanFinalized(plan_id="p1", approved_item_ids=["i1"]))
    _round_trip(ev.ApplyStarted(plan_id="p1"))
    _round_trip(ev.ActionApplied(item_id="i1", status="ok", message=None))
    _round_trip(ev.UndoPerformed(checkpoint_path=tmp_path / "ckpt.json"))

