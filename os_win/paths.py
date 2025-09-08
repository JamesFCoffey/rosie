"""Windows path helpers.

This module provides utilities for Windows-specific path handling while remaining
safe to import and use on non-Windows platforms. Functions are no-ops where
appropriate outside Windows so tests can run cross-platform.

Key features:
- Extended-length (``\\\\?\\``) path normalization for long paths
- A small helper to resolve common "known folders" in a privacy-friendly way

The helpers avoid any outbound network calls and do not perform I/O themselves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict


_EXTENDED_PREFIX = "\\\\?\\"


def _is_windows() -> bool:
    """Return True when running on Windows."""
    # Using os.name is enough here and avoids importing platform.
    import os

    return os.name == "nt"


def to_long_path(p: Path) -> Path:
    """Normalize ``p`` to an extended-length path on Windows.

    On Windows, returns a path with the ``\\\\?\\`` prefix (or
    ``\\\\?\\UNC\\`` for UNC paths). On non-Windows platforms, returns ``p``
    unchanged. The function does not touch the filesystem; it only returns a
    normalized representation suitable for long-path operations.

    Args:
      p: The input path (relative or absolute).

    Returns:
      A ``Path`` that is identical to ``p`` on non-Windows, or uses the
      extended-length prefix on Windows.
    """
    if not _is_windows():
        return p

    # Build an absolute form without requiring existence. ``resolve`` with
    # ``strict=False`` normalizes segments while avoiding failures.
    try:
        abs_path = p.resolve(strict=False)
    except Exception:
        # As a conservative fallback, use ``absolute`` which does not consult
        # the filesystem. This keeps behavior predictable even for non-existing
        # paths or when permissions are restricted.
        abs_path = p.absolute()

    s = str(abs_path)

    # If already extended-length, return as Path directly.
    if s.startswith(_EXTENDED_PREFIX) or s.startswith("\\\\.\\"):
        return Path(s)

    # UNC path: \\server\share -> \\?\UNC\server\share
    if s.startswith("\\\\"):
        # Strip exactly two leading backslashes, then prepend UNC extended form.
        # Example: \\server\share -> server\share
        tail = s.lstrip("\\")
        return Path(_EXTENDED_PREFIX + "UNC\\" + tail)

    # Drive-letter or absolute local path: C:\foo -> \\?\C:\foo
    return Path(_EXTENDED_PREFIX + s)


def get_known_folder(name: str) -> Path:
    """Return the path to a known folder in a privacy-friendly way.

    Only uses environment variables and simple conventions; does not call into
    any Windows shell APIs. On non-Windows, returns sensible defaults.

    Supported names (case-insensitive):
      - "home"
      - "desktop"
      - "downloads"
      - "documents"
      - "appdata" (Roaming)
      - "local_appdata"
      - "temp"

    Args:
      name: The known folder identifier.

    Returns:
      A Path pointing to the known folder.

    Raises:
      ValueError: If ``name`` is not a supported known folder.
    """
    n = name.strip().lower()

    home = Path.home()
    if n == "home":
        return home

    # Basic, environment-variable-based mapping. Avoids shell APIs for privacy
    # and to keep the code self-contained and testable cross-platform.
    env: Dict[str, str] = {}
    try:
        import os

        env = dict(os.environ)
    except Exception:
        env = {}

    if _is_windows():
        userprofile = Path(env.get("USERPROFILE", str(home)))
        # Roaming and local appdata; fall back to standard conventions.
        appdata = Path(env.get("APPDATA", str(userprofile / "AppData" / "Roaming")))
        local_appdata = Path(env.get("LOCALAPPDATA", str(userprofile / "AppData" / "Local")))
        temp = Path(env.get("TEMP", env.get("TMP", str(local_appdata / "Temp"))))

        mapping: Dict[str, Path] = {
            "desktop": userprofile / "Desktop",
            "downloads": userprofile / "Downloads",
            "documents": userprofile / "Documents",
            "appdata": appdata,
            "local_appdata": local_appdata,
            "temp": temp,
        }
    else:
        # Cross-platform sensible defaults.
        temp = Path(env.get("TMPDIR", "/tmp"))
        mapping = {
            "desktop": home / "Desktop",
            "downloads": home / "Downloads",
            "documents": home / "Documents",
            "appdata": home / ".config",
            "local_appdata": home / ".local" / "share",
            "temp": temp,
        }

    if n in mapping:
        return mapping[n]

    raise ValueError(f"Unsupported known folder: {name}")


__all__ = ["to_long_path", "get_known_folder"]
