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
    # Legacy include/exclude (globs)
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    # New matching fields
    paths: List[str] = Field(default_factory=list)
    globs: List[str] = Field(default_factory=list)
    exts: List[str] = Field(default_factory=list)
    allow: List[str] = Field(default_factory=list)
    deny: List[str] = Field(default_factory=list)
    # Optional size/age constraints
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    min_age_days: Optional[float] = None
    max_age_days: Optional[float] = None
    action: str = "info"
    reason: Optional[str] = None


class RuleSet(_JsonMixin):
    rules: List[Rule] = Field(default_factory=list)
