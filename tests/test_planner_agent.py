from __future__ import annotations

import asyncio
from pathlib import Path

from agents.planner_agent import PlannerAgent
from projections.base import replay
from projections.plan_view import PlanProjection
from storage.event_store import EventStore
from tools import file_scanner


def _db(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


def _write(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_planner_emits_events_and_plan_matches_rules(tmp_path: Path) -> None:
    # Workspace
    ws = tmp_path / "ws"
    f_txt = ws / "doc.txt"
    f_log = ws / "app.log"
    _write(f_txt, "hello world")
    _write(f_log, "log entry")

    # Rules file matching both extensions
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(
        """
        {"rules": [
            {"id": "Rtxt", "name": "txt", "globs": ["*.txt"], "action": "info"},
            {"id": "Rlog", "name": "log", "globs": ["*.log"], "action": "info"}
        ]}
        """.strip()
    )

    store = EventStore(_db(tmp_path))
    try:
        # Emit a full scan with batches
        total = asyncio.run(file_scanner.scan_and_emit(root=ws, store=store, batch_size=128))
        assert total >= 2

        # Run planner without semantics (rules only)
        planner = PlannerAgent(store)
        planner.propose_plan(root=ws, semantic=False, rules_path=rules_file)

        rows = store.read_all()
        types = [r.type for r in rows]
        # Ensure RuleMatched and PlanProposed are present
        assert "RuleMatched" in types
        assert types[-1] == "PlanProposed"

        # Materialize the plan and check items reflect rules
        proj = PlanProjection()
        replay(proj, store)
        plan = proj.current_plan()
        actions = sorted(i.action for i in plan.items)
        assert actions == ["rule:Rlog", "rule:Rtxt"]
        # Reasons/confidences populated
        assert all(i.reason and 0.0 <= i.confidence <= 1.0 for i in plan.items)
    finally:
        store.close()


def test_planner_with_semantic_emits_clusters(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    a = ws / "notes_alpha.txt"
    b = ws / "notes_beta.txt"
    c = ws / "image.png"
    _write(a, "alpha beta")
    _write(b, "alpha gamma")
    _write(c, "zeta xi")

    store = EventStore(_db(tmp_path))
    try:
        asyncio.run(file_scanner.scan_and_emit(root=ws, store=store))

        planner = PlannerAgent(store)
        planner.propose_plan(root=ws, semantic=True, rules_path=None)

        rows = store.read_all()
        # Expect a ClustersFormed somewhere before PlanProposed
        types = [r.type for r in rows]
        assert "ClustersFormed" in types
        assert types[-1] == "PlanProposed"
    finally:
        store.close()
