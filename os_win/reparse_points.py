"""Reparse point and junction detection.

This module exposes a small helper to determine whether a path is a Windows
reparse point (e.g., a junction or symlink). On non-Windows platforms the
function treats symbolic links as reparse points and regular paths as normal.

The implementation is careful to work without requiring special privileges and
avoids following links by using ``lstat`` when available.
"""

from __future__ import annotations

import os
from pathlib import Path

# FILE_ATTRIBUTE_REPARSE_POINT from WinBase.h
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


def is_reparse_point(p: Path) -> bool:
    """Return True if ``p`` is a reparse point (junction/symlink).

    On Windows, uses the file attribute flag to detect reparse points without
    following them. On non-Windows, returns ``True`` for symbolic links and
    ``False`` otherwise.

    Args:
      p: Path to test (does not need to exist if it's a symlink).

    Returns:
      True when the path is a reparse point or symlink as described above.
    """
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        # Broken symlink: on POSIX, lstat still works and we wouldn't be here.
        # On Windows, treat non-existing as not a reparse point.
        return False

    # Windows exposes st_file_attributes; guard access for portability.
    attrs = getattr(st, "st_file_attributes", None)
    if attrs is not None:
        return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)

    # POSIX fallback: treat symlinks as reparse points for our purposes.
    return Path(p).is_symlink()


__all__ = ["is_reparse_point"]
