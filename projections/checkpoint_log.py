"""Checkpoint log projection (stub)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class CheckpointEntry:
    checkpoint_path: Path


@dataclass
class CheckpointLog:
    entries: List[CheckpointEntry]

