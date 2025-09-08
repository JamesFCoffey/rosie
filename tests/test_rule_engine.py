from __future__ import annotations

import json
import os
import time
from pathlib import Path

from projections.base import replay
from projections.plan_view import PlanProjection
from schemas.rules import Rule, RuleSet
from storage.event_store import EventStore
from tools import rule_engine


def _db_path(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


def _touch(p: Path, size: int = 1, age_days: float | None = None) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x" * size)
    if age_days is not None:
        now = time.time()
        past = now - age_days * 86400.0
        os.utime(p, (past, past))


def test_rule_precedence_and_conditions(tmp_path: Path) -> None:
    # Files
    a = tmp_path / "exact.txt"
    b = tmp_path / "notes.md"
    c = tmp_path / "big.log"
    _touch(a, size=10, age_days=5.0)
    _touch(b, size=1, age_days=0.1)
    _touch(c, size=10_000, age_days=30.0)

    rules = RuleSet(
        rules=[
            # ext rule (lowest)
            Rule(id="Rext", name="ext-md", exts=[".md"], action="info"),
            # glob rule (overrides ext)
            Rule(id="Rglob", name="glob-notes", globs=["notes.*"], action="info"),
            # path rule (highest)
            Rule(id="Rpath", name="exact-file", paths=[str(a.name)], action="info"),
            # size/age constrained rule
            Rule(
                id="RsizeAge",
                name="old-large-logs",
                globs=["*.log"],
                min_size=5_000,
                min_age_days=7.0,
                action="info",
            ),
            # deny list should exclude
            Rule(id="Rdeny", name="deny-notes", globs=["*.md"], deny=["notes.md"], action="info"),
        ]
    )

    matches = rule_engine.match_rules([a, b, c], rules)

    # Precedence: a -> Rpath, b -> Rglob (over ext), c -> RsizeAge
    assert matches.get(a) == "Rpath"
    assert matches.get(b) == "Rglob"
    assert matches.get(c) == "RsizeAge"


def test_yaml_loader_and_event_emission(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    f1 = ws / "doc.txt"
    f2 = ws / "image.jpg"
    _touch(f1, size=100)
    _touch(f2, size=200)

    # Write rules as YAML if available, else JSON; loader supports both
    rules_file = tmp_path / "rules.yaml"
    content = {
        "rules": [
            {"id": "Rtxt", "name": "txt", "globs": ["*.txt"], "action": "info"},
            {"id": "Rimg", "name": "img", "exts": [".jpg"], "action": "info"},
        ]
    }
    try:
        import yaml  # type: ignore

        rules_file.write_text(yaml.safe_dump(content))
    except Exception:
        rules_file.write_text(json.dumps(content))

    rules = rule_engine.load_rules_from_yaml(rules_file)

    store = EventStore(_db_path(tmp_path))
    try:
        emitted = rule_engine.emit_rule_matches([f1, f2], rules, store)
        assert emitted == 2

        # Reconstruct plan from events and confirm deterministic items
        proj = PlanProjection()
        replay(proj, store)
        plan = proj.current_plan()
        # There should be 2 items, one per RuleMatched
        assert len(plan.items) == 2
        actions = sorted(i.action for i in plan.items)
        assert actions == ["rule:Rimg", "rule:Rtxt"]
    finally:
        store.close()

