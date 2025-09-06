"""File index projection (stub)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass
class FileIndex:
    entries: Dict[Path, dict]

