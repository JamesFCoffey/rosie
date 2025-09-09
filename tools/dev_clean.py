"""Developer cache detector and sizer.

Finds common development build/cache directories under a root and reports their
sizes. Used by the ``rosie dev-clean`` CLI to present a dry-run summary and to
optionally remove caches (handled by the orchestrator using Windows-safe ops).

This module performs no deletions; it is pure discovery + sizing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Canonical cache directory patterns; paths are matched via Path.rglob and can
# include simple subpath globs like ".next/cache".
DEV_CACHE_DIRS: list[str] = [
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

# Preset mapping to subsets. Presets are conservative; "all" is the union.
PRESETS: dict[str, list[str]] = {
    "all": DEV_CACHE_DIRS,
    "node": [
        "node_modules",
        ".next/cache",
        ".parcel-cache",
        "dist",
        "build",
        ".cache",
    ],
    "python": [
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".tox",
        "build",
        "dist",
        ".cache",
    ],
    # Keep placeholder for future; currently behaves as no-op specialization
    "docker": [
        ".cache",
        "build",
    ],
}


@dataclass
class DevCacheFinding:
    path: Path
    size_mb: float


def find_dev_caches(root: Path, *, preset: str = "all") -> list[DevCacheFinding]:
    """Find dev cache directories under ``root``.

    Args:
        root: Root directory to search.
        preset: One of presets in ``PRESETS`` (e.g., "all", "node", "python").

    Returns:
        List of findings with resolved paths and sizes in MB.
    """
    root = root.resolve()
    seen: set[Path] = set()
    results: list[DevCacheFinding] = []
    patterns = PRESETS.get(preset.lower(), DEV_CACHE_DIRS)
    for pat in patterns:
        for p in root.rglob(pat):
            try:
                if not p.exists() or not p.is_dir():
                    continue
            except OSError:
                continue
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            size_mb = _dir_size_mb(rp)
            results.append(DevCacheFinding(path=rp, size_mb=size_mb))
    return results


def _dir_size_mb(path: Path) -> float:
    """Compute directory size in MB, best-effort and safe.

    Skips entries that cannot be stat'ed to avoid breaking discovery on
    permission/reparse issues.
    """
    total = 0
    try:
        it = path.rglob("*")
    except Exception:
        it = []  # type: ignore[assignment]
    for file in it:
        try:
            if file.is_file():
                total += file.stat().st_size
        except OSError:
            continue
    return total / (1024 * 1024)
