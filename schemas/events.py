"""Pydantic event models and JSON helpers.

Defines domain event models with a stable ``type`` field and provides
``to_json``/``from_json`` helpers for round-trip serialization.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel


class _JsonMixin(BaseModel):
    """Common JSON helpers for schemas.

    Uses Pydantic v2 ``model_dump_json`` / ``model_validate_json``.
    """

    def to_json(self) -> str:
        """Serialize the model to a JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str):  # type: ignore[override]
        """Deserialize a JSON string into the model type."""
        return cls.model_validate_json(data)


class FilesScanned(_JsonMixin):
    type: str = "FilesScanned"
    root: Path
    count: int
    # Optional batch payload for detailed scanning; backward-compatible
    batch: Optional[List[dict]] = None


class RuleMatched(_JsonMixin):
    type: str = "RuleMatched"
    path: Path
    rule_id: str


class EmbeddingsComputed(_JsonMixin):
    type: str = "EmbeddingsComputed"
    count: int


class ClustersFormed(_JsonMixin):
    type: str = "ClustersFormed"
    count: int


class PlanProposed(_JsonMixin):
    type: str = "PlanProposed"
    plan_id: str
    item_ids: List[str]


class UserApproved(_JsonMixin):
    type: str = "UserApproved"
    plan_id: str
    item_ids: List[str]


class CorrectionAdded(_JsonMixin):
    type: str = "CorrectionAdded"
    plan_id: str
    note: str


class PlanFinalized(_JsonMixin):
    type: str = "PlanFinalized"
    plan_id: str
    approved_item_ids: List[str]


class ApplyStarted(_JsonMixin):
    type: str = "ApplyStarted"
    plan_id: str


class ActionApplied(_JsonMixin):
    type: str = "ActionApplied"
    item_id: str
    status: str
    message: Optional[str] = None


class UndoPerformed(_JsonMixin):
    type: str = "UndoPerformed"
    checkpoint_path: Path
