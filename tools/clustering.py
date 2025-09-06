"""Clustering (stub)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List


def cluster_by_extension(paths: Iterable[Path]) -> Dict[str, List[Path]]:
    groups: Dict[str, List[Path]] = {}
    for p in paths:
        ext = p.suffix.lower() or "<none>"
        groups.setdefault(ext, []).append(p)
    return groups

