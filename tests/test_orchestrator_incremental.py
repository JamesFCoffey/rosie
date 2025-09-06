from __future__ import annotations

import asyncio
from pathlib import Path

from core.graph import Orchestrator
from schemas import events as ev
from schemas.rules import Rule, RuleSet
from storage.event_store import EventStore


def _db_path(tmp_path: Path) -> Path:
    # Place the DB outside the scanned workspace to avoid interference
    return (tmp_path / "state").joinpath("events.db")


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")


def test_incremental_invalidation_scoped(tmp_path: Path) -> None:
    # Arrange: files and rules
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
        # Seed a scan event; orchestrator will perform the actual scan
        store.append(ev.FilesScanned(root=ws, count=2))
        asyncio.run(orch.run_once())

        stats = orch.run_stats
        assert stats.scanner_runs == 1
        assert stats.rule_runs == 1
        assert stats.cluster_runs == 1
        # Both files were evaluated on first run
        assert stats.rule_paths_evaluated == 2
        assert stats.cluster_paths_evaluated == 2

        # Add a correction scoped to a single path
        store.append(ev.CorrectionAdded(plan_id="p1", note="rename (path=a.txt)"))
        asyncio.run(orch.run_once())

        stats = orch.run_stats
        # Scanner should not re-run for a scoped correction
        assert stats.scanner_runs == 1
        # Rules + clustering should run, but only for the one impacted path
        assert stats.rule_runs == 2
        assert stats.cluster_runs == 2
        assert stats.rule_paths_evaluated == 1
        assert stats.cluster_paths_evaluated == 1
    finally:
        store.close()


def test_incremental_invalidation_global(tmp_path: Path) -> None:
    # Arrange
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "f1.txt").write_text("x")
    (ws / "f2.log").write_text("y")
    rules = RuleSet(rules=[
        Rule(id="R1", name="txt", include=["*.txt"], exclude=[]),
        Rule(id="R2", name="log", include=["*.log"], exclude=[]),
    ])
    store = EventStore(_db_path(tmp_path))
    orch = Orchestrator(db_path=_db_path(tmp_path))
    orch.set_rules(rules)

    try:
        store.append(ev.FilesScanned(root=ws, count=2))
        asyncio.run(orch.run_once())

        # Global correction (no path hint) forces full pipeline
        store.append(ev.CorrectionAdded(plan_id="p1", note="rename something"))
        asyncio.run(orch.run_once())

        stats = orch.run_stats
        assert stats.scanner_runs == 2  # scanner re-runs on global invalidation
        assert stats.rule_runs == 2
        assert stats.cluster_runs == 2
        # On full run, both paths are evaluated
        assert stats.rule_paths_evaluated == 2
        assert stats.cluster_paths_evaluated == 2
    finally:
        store.close()
