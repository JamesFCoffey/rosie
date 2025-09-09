"""Pytest configuration and shared fixtures.

Ensures the repository root is importable (so tests can import packages like
`cli`, `core`, `tools` without an editable install), and provides a couple of
simple helpers for temporary trees and Windows path cases.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make repo root importable for tests (avoid requiring `pip install -e .`).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def chdir_tmp_path(tmp_path: Path) -> Path:
    """Change CWD to a fresh tmp path for isolation.

    Returns:
        The temporary directory path now set as the process CWD.
    """
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(cwd)


@pytest.fixture
def make_tree(tmp_path: Path):
    """Factory to create a file tree under ``tmp_path``.

    Example:
        make_tree({"a/b.txt": "hello", "empty/": None})
    """

    def _make(spec: dict[str, str | bytes | None], *, root: Path | None = None) -> Path:
        base = root or tmp_path
        for rel, content in spec.items():
            p = base / rel
            if rel.endswith(":") or rel.endswith(":/"):
                # Allow colon suffix to force directory, but normalize
                p = base / rel.rstrip(":/")
                p.mkdir(parents=True, exist_ok=True)
                continue
            if rel.endswith("/"):
                p.mkdir(parents=True, exist_ok=True)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            if content is None:
                p.touch()
            elif isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(content, encoding="utf-8")
        return base

    return _make


@pytest.fixture
def long_path(tmp_path: Path) -> tuple[Path, Path]:
    """Return a path pair (normal, maybe-long) to exercise Windows prefixing.

    The second element is a path whose textual representation is long enough
    that Windows code paths may apply the ``\\\\?\\`` long-path prefix.
    On non-Windows systems, these are just normal paths.
    """
    tail = "nested" * 40
    p = tmp_path / tail / "file.txt"
    return tmp_path, p

