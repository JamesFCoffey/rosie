"""Plan schemas and JSON helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound="_JsonMixin")


class _JsonMixin(BaseModel):
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls: type[T], data: str) -> T:
        return cls.model_validate_json(data)


class PlanItemModel(_JsonMixin):
    id: str
    action: str
    target: Path
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class PlanModel(_JsonMixin):
    id: str
    items: list[PlanItemModel]
