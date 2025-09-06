"""Checkpoint schemas (skeleton)."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel


class CheckpointAction(BaseModel):
    item_id: str
    op: str
    src: Path
    dst: Path | None = None


class Checkpoint(BaseModel):
    path: Path
    actions: List[CheckpointAction]

