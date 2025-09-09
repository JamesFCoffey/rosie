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


def test_hidden_files_excluded_by_default(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    visible = ws / "visible.txt"
    hidden = ws / ".secret.txt"
    _write(visible, "ok")
    _write(hidden, "nope")

    store = EventStore(_db(tmp_path))
    try:
        # Scanner should skip hidden file by default
        total = asyncio.run(file_scanner.scan_and_emit(root=ws, store=store))
        # Expect 2 directories (ws and maybe parent) + 1 visible file in total batches, but
        # most importantly, ensure hidden is not in index-derived plan.
        assert total >= 1

        planner = PlannerAgent(store)
        planner.propose_plan(root=ws, semantic=False, rules_path=None)

        proj = PlanProjection()
        replay(proj, store)
        plan = proj.current_plan()
        # No rule actions without rules; ensure that hidden didn't accidentally create entries
        # under RuleMatched, and if clusters emit moves, they must not target hidden.
        for it in plan.items:
            assert ".secret" not in str(it.target)
    finally:
        store.close()
