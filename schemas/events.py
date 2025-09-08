"""Pydantic event models and JSON helpers.

Defines domain event models with a stable ``type`` field and provides
``to_json``/``from_json`` helpers for round-trip serialization.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


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
    # Optional per-item assignments for downstream projections
    # Each item may carry an optional cluster label; items with cluster_id = -1 are noise.
    items: Optional[List["ClusterAssignment"]] = None


class ClusterAssignment(_JsonMixin):
    """Cluster assignment payload for ``ClustersFormed`` events.

    Attributes:
        path: Source file path.
        cluster_id: Cluster numeric id; ``-1`` denotes noise/outlier.
        confidence: Membership confidence in [0, 1].
        label: Optional human-friendly label for the cluster.
    """

    path: Path
    cluster_id: int
    confidence: float = Field(ge=0.0, le=1.0)
    label: Optional[str] = None


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
