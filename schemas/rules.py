"""Rule schemas (skeleton)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class Rule(BaseModel):
    id: str
    name: str
    include: List[str] = []
    exclude: List[str] = []
    action: str = "info"
    reason: Optional[str] = None


class RuleSet(BaseModel):
    rules: List[Rule] = []

