"""Pydantic event models (skeleton)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel


class FilesScanned(BaseModel):
    root: Path
    count: int


class RuleMatched(BaseModel):
    path: Path
    rule_id: str


class EmbeddingsComputed(BaseModel):
    count: int


class ClustersFormed(BaseModel):
    count: int


class PlanProposed(BaseModel):
    plan_id: str
    item_ids: List[str]


class UserApproved(BaseModel):
    plan_id: str
    item_ids: List[str]


class CorrectionAdded(BaseModel):
    plan_id: str
    note: str


class PlanFinalized(BaseModel):
    plan_id: str
    approved_item_ids: List[str]


class ApplyStarted(BaseModel):
    plan_id: str


class ActionApplied(BaseModel):
    item_id: str
    status: str
    message: Optional[str] = None


class UndoPerformed(BaseModel):
    checkpoint_path: Path

