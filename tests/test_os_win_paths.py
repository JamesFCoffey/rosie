from __future__ import annotations

import sys
from pathlib import Path

from os_win.paths import get_known_folder, to_long_path


def test_get_known_folder_home() -> None:
    assert get_known_folder("home") == Path.home()


def test_get_known_folder_common() -> None:
    # Should return a Path even if the directory does not exist
    for name in ["desktop", "downloads", "documents", "temp", "appdata", "local_appdata"]:
        try:
            p = get_known_folder(name)
        except ValueError:
            # Non-Windows may raise for some names; ensure at least 'temp' works
            if name in {"appdata", "local_appdata"} and sys.platform != "win32":
                continue
            raise
        assert isinstance(p, Path)


def test_to_long_path_prefix(tmp_path: Path) -> None:
    # Build a long-ish path textually (no need to create on disk)
    long_tail = "nested" * 40
    p = (tmp_path / long_tail)
    lp = to_long_path(p)
    if sys.platform == "win32":
        s = str(lp)
        assert s.startswith("\\\\?\\") or s.startswith("\\\\?\\UNC\\")
    else:
        assert lp == p

