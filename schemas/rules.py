"""Rule schemas and JSON helpers."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class _JsonMixin(BaseModel):
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str):  # type: ignore[override]
        return cls.model_validate_json(data)


class Rule(_JsonMixin):
    id: str
    name: str
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    action: str = "info"
    reason: Optional[str] = None


class RuleSet(_JsonMixin):
    rules: List[Rule] = Field(default_factory=list)
