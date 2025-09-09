from __future__ import annotations

import os
from pathlib import Path

from os_win.recycle_bin import send_to_recycle_bin


def test_send_to_recycle_bin_is_noop_on_non_windows(tmp_path: Path) -> None:
    p = tmp_path / "sample.txt"
    p.write_text("hello")

    # On non-Windows runners, this should be a no-op and not delete the file
    send_to_recycle_bin(p)

    if os.name != "nt":
        assert p.exists()

