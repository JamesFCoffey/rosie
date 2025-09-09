from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cli.main import app


runner = CliRunner()


DEV_DIRS = [
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".tox",
    ".gradle",
    ".m2",
    ".next/cache",
    "dist",
    "build",
    ".cache",
    ".parcel-cache",
]


def _touch(path: Path, size: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        if size > 0:
            f.write(b"x" * size)


def _make_dev_tree(root: Path) -> list[Path]:
    created: list[Path] = []
    for d in DEV_DIRS:
        p = root / d
        p.mkdir(parents=True, exist_ok=True)
        # Add a small file so size > 0 for most
        _touch(p / "dummy.bin", size=2048)
        created.append(p)
    return created


def test_dev_clean_cli_dry_run_lists_caches(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    created = _make_dev_tree(root)

    res = runner.invoke(app, ["dev-clean", str(root)])
    assert res.exit_code == 0
    out = res.stdout
    # Should show keep action (dry-run) and list some known dirs
    assert "Dev Clean Report" in out
    assert "keep" in out
    # Spot-check a few entries by leaf name
    assert "node_modules" in out
    assert ".venv" in out
    assert "__pycache__" in out or ".pytest_cache" in out


def test_dev_clean_cli_apply_deletes_on_non_windows(tmp_path: Path) -> None:
    root = tmp_path / "proj2"
    root.mkdir()
    created = _make_dev_tree(root)

    res = runner.invoke(app, ["dev-clean", str(root), "--apply"])  # flips dry-run flag off
    assert res.exit_code == 0
    out = res.stdout
    assert "delete" in out

    # On non-Windows test runners, directories should be removed
    import os

    if os.name != "nt":
        for p in created:
            assert not p.exists()

