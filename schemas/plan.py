"""Plan schemas (skeleton)."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field


class PlanItemModel(BaseModel):
    id: str
    action: str
    target: Path
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class PlanModel(BaseModel):
    id: str
    items: List[PlanItemModel]

