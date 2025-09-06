"""Checkpoint schemas and JSON helpers."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel


class _JsonMixin(BaseModel):
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str):  # type: ignore[override]
        return cls.model_validate_json(data)


class CheckpointAction(_JsonMixin):
    item_id: str
    op: str
    src: Path
    dst: Path | None = None


class Checkpoint(_JsonMixin):
    path: Path
    actions: List[CheckpointAction]
