from __future__ import annotations

import asyncio
from pathlib import Path

from core.graph import Orchestrator
from schemas import events as ev
from schemas.rules import Rule, RuleSet
from storage.event_store import EventStore


def _db_path(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")


def test_plan_updates_and_hash_changes_on_correction(tmp_path: Path) -> None:
    # Arrange workspace with two files and simple rules
    ws = tmp_path / "ws"
    a = ws / "a.txt"
    b = ws / "b.log"
    _touch(a)
    _touch(b)

    rules = RuleSet(rules=[
        Rule(id="R1", name="txt", include=["*.txt"], exclude=[]),
        Rule(id="R2", name="log", include=["*.log"], exclude=[]),
    ])

    store = EventStore(_db_path(tmp_path))
    orch = Orchestrator(db_path=_db_path(tmp_path))
    orch.set_rules(rules)

    try:
        # Seed a scan event and run orchestrator to materialize initial plan via RuleMatched events
        store.append(ev.FilesScanned(root=ws, count=2))
        asyncio.run(orch.run_once())

        before_id = orch.current_plan_id
        assert before_id is not None

        # Add a path-scoped correction; orchestrator should re-evaluate only that path
        store.append(ev.CorrectionAdded(plan_id=before_id, note="fix name (path=a.txt)"))
        asyncio.run(orch.run_once())

        after_id = orch.current_plan_id
        assert after_id is not None
        assert after_id != before_id  # correction bumps plan generation/hash

        # Verify partial recompute via counters
        stats = orch.run_stats
        assert stats.scanner_runs == 1  # no rescan for scoped correction
        assert stats.rule_runs == 2
        assert stats.cluster_runs == 2
        assert stats.rule_paths_evaluated == 1
        assert stats.cluster_paths_evaluated == 1
    finally:
        store.close()

