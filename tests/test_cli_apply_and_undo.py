from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def _write_plan(path: Path, *, target: Path) -> Path:
    data = {
        "id": "test-plan-1",
        "items": [
            {
                "id": "item-1",
                "action": "create_dir",
                "target": str(target),
                "reason": "create for test",
                "confidence": 1.0,
            }
        ],
    }
    path.write_text(json.dumps(data))
    return path


def test_cli_apply_requires_yes(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    target = tmp_path / "newdir"
    _write_plan(plan_path, target=target)

    result = runner.invoke(app, ["apply", "--plan", str(plan_path)])
    assert result.exit_code != 0
    assert "Refusing to apply without --yes" in result.stdout


def test_cli_apply_creates_checkpoint_and_dir_then_undo(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    target = tmp_path / "newdir"
    ckpt_path = tmp_path / "ckpt.json"
    _write_plan(plan_path, target=target)

    # Apply with --yes
    result = runner.invoke(
        app, ["apply", "--plan", str(plan_path), "--checkpoint", str(ckpt_path), "--yes"]
    )
    assert result.exit_code == 0
    assert target.exists() and target.is_dir()
    assert ckpt_path.exists()
    # Journal contains the mkdir action
    data = json.loads(ckpt_path.read_text())
    acts = data.get("actions") or []
    assert any(a.get("op") == "mkdir" and Path(a.get("src")) == target for a in acts)

    # Undo should remove the directory (on non-Windows direct delete is used)
    result2 = runner.invoke(app, ["undo", "--checkpoint", str(ckpt_path)])
    assert result2.exit_code == 0
    assert not target.exists()

    # Idempotent undo: second run should not raise and keep state
    result3 = runner.invoke(app, ["undo", "--checkpoint", str(ckpt_path)])
    assert result3.exit_code == 0
