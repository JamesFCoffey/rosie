"""OneDrive helpers.

Provides a conservative heuristic to detect whether a path lives under a
OneDrive-controlled folder. On Windows, checks common environment variables
and well-known folder names. On non-Windows, falls back to path segment name
matching so tests can simulate OneDrive paths.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def _segments(p: Path) -> Iterable[str]:
    try:
        return [s.lower() for s in p.resolve(strict=False).parts]
    except Exception:
        return [s.lower() for s in p.parts]


def is_onedrive_path(p: Path) -> bool:
    """Return True if the path appears to be under OneDrive.

    Heuristics:
    - Any path segment containing "onedrive" (case-insensitive)
    - Matches environment-provided OneDrive directories on Windows
    """
    parts = list(_segments(Path(p)))
    if any("onedrive" in seg for seg in parts):
        return True
    # Environment variables on Windows
    try:
        import os as _os

        for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
            v = _os.environ.get(var)
            if v and Path(v).resolve(strict=False) in Path(p).resolve(strict=False).parents:
                return True
    except Exception:
        pass
    return False
