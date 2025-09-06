"""Dev cache detector (stub)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


DEV_CACHE_DIRS = [
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


@dataclass
class DevCacheFinding:
    path: Path
    size_mb: float


def find_dev_caches(root: Path, *, preset: str = "all") -> List[DevCacheFinding]:
    root = root.resolve()
    results: List[DevCacheFinding] = []
    patterns = DEV_CACHE_DIRS if preset.lower() == "all" else DEV_CACHE_DIRS
    for pat in patterns:
        for p in root.rglob(pat):
            if p.is_dir():
                size_mb = _dir_size_mb(p)
                results.append(DevCacheFinding(path=p, size_mb=size_mb))
    return results


def _dir_size_mb(path: Path) -> float:
    total = 0
    for file in path.rglob("*"):
        try:
            if file.is_file():
                total += file.stat().st_size
        except OSError:
            continue
    return total / (1024 * 1024)

