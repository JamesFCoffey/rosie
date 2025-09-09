"""Rule schemas and JSON helpers."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound="_JsonMixin")


class _JsonMixin(BaseModel):
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls: type[T], data: str) -> T:
        return cls.model_validate_json(data)


class Rule(_JsonMixin):
    id: str
    name: str
    # Legacy include/exclude (globs)
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    # New matching fields
    paths: list[str] = Field(default_factory=list)
    globs: list[str] = Field(default_factory=list)
    exts: list[str] = Field(default_factory=list)
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    # Optional size/age constraints
    min_size: int | None = None
    max_size: int | None = None
    min_age_days: float | None = None
    max_age_days: float | None = None
    action: str = "info"
    reason: str | None = None


class RuleSet(_JsonMixin):
    rules: list[Rule] = Field(default_factory=list)
