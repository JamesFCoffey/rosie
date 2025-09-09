from __future__ import annotations

import asyncio
from pathlib import Path

from agents.planner_agent import PlannerAgent
from agents.reviewer_agent import ReviewerAgent
from storage.event_store import EventStore
from tools import file_scanner


def _db(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


def _write(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_tui_commands_map_to_events(tmp_path: Path) -> None:
    # Arrange: workspace with files and simple rules covering both files
    ws = tmp_path / "ws"
    f_txt = ws / "note.txt"
    f_log = ws / "server.log"
    _write(f_txt, "hello")
    _write(f_log, "log")

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
        # Emit scan events and propose a plan
        asyncio.run(file_scanner.scan_and_emit(root=ws, store=store))
        planner = PlannerAgent(store)
        view = planner.propose_plan(root=ws, semantic=False, rules_path=rules_file)

        # Pick two IDs to approve; the rest will be used in corrections
        assert len(view.items) >= 2
        id1 = view.items[0].id
        id2 = view.items[1].id

        reviewer = ReviewerAgent(store)
        cmds = [
            f"approve {id1},{id2}",
            f"reject {id1} low confidence",
            f"relabel {id1} important cluster",
            f"split {id1} into sub-actions",
            f"merge {id1},{id2} consolidate",
            "exclude **/.cache/**",
            "rule {\"id\": \"Inline\", \"globs\": [\"*.tmp\"]}",
        ]

        result = reviewer.review(view, commands=cmds)

        # Validate in-memory result
        assert set(result.approved_item_ids) == {id1, id2}
        assert any(c.startswith(f"reject:{id1}") for c in result.corrections)
        assert any(c.startswith(f"relabel:{id1}:") for c in result.corrections)
        assert any(c.startswith(f"split:{id1}:") for c in result.corrections)
        assert any(c.startswith("merge:") for c in result.corrections)
        assert any(c.startswith("exclude:") for c in result.corrections)
        assert any(c.startswith("rule:") for c in result.corrections)

        # Validate events appended to the store
        rows = store.read_all()
        types = [r.type for r in rows]
        assert "UserApproved" in types
        corr_notes = [r.data.get("note", "") for r in rows if r.type == "CorrectionAdded"]
        assert any(n.startswith("reject:") for n in corr_notes)
        assert any(n.startswith("relabel:") for n in corr_notes)
        assert any(n.startswith("split:") for n in corr_notes)
        assert any(n.startswith("merge:") for n in corr_notes)
        assert any(n.startswith("exclude:") for n in corr_notes)
        assert any(n.startswith("rule:") for n in corr_notes)
    finally:
        store.close()

