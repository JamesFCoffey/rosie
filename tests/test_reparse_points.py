from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from os_win.reparse_points import is_reparse_point


def test_is_reparse_point_regular_dir(tmp_path: Path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    assert is_reparse_point(d) is False


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation may require privileges on Windows")
def test_is_reparse_point_symlink(tmp_path: Path) -> None:
    d = tmp_path / "target"
    d.mkdir()
    link = tmp_path / "link"
    os.symlink(d, link, target_is_directory=True)
    assert is_reparse_point(link) is True

