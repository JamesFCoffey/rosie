from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def _write(p: Path, size: int = 1) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * max(0, size))


def test_cli_scan_smoke_displays_plan_and_folders(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root / "a" / "x1.dat", 100)
    _write(root / "a" / "b" / "y2.dat", 200)

    db = tmp_path / "events.db"
    res = runner.invoke(
        app,
        [
            "scan",
            str(root),
            "--limit",
            "5",
            "--db",
            str(db),
        ],
    )
    assert res.exit_code == 0
    out = res.stdout
    assert "Proposed Plan (dry-run)" in out
    # Largest folders table should be printed when batches are emitted
    assert "Largest Folders" in out
