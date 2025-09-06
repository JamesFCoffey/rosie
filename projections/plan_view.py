"""Plan view projection and UI models.

This module provides:
- Lightweight Pydantic models ``PlanItem``/``PlanView`` for CLI display
  (used by the orchestrator stub), and
- A deterministic ``PlanProjection`` that replays events into a stable plan
  and computes a content-addressed plan id (hash) for reproducible replays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field

from schemas.plan import PlanItemModel, PlanModel
from storage.event_store import EventRecord, compute_checksum


class PlanItem(BaseModel):
    id: str
    action: str
    target: Path
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class PlanView(BaseModel):
    items: List[PlanItem] = []


@dataclass
class PlanProjection:
    """Deterministic plan materialized view.

    Merges rule matches (and, in the future, clusters) into a plan. The plan id
    is a stable hash of the sorted items along with a correction generation
    counter that increments on ``CorrectionAdded`` events.
    """

    items: Dict[str, PlanItemModel] = field(default_factory=dict)
    correction_gen: int = 0

    def apply(self, event: EventRecord) -> None:
        """Apply a single event to update the plan state."""
        et = event.type
        data = event.data

        if et == "RuleMatched":
            # Deterministic item construction from event payload only.
            path = Path(data["path"])  # Pydantic serializes Path -> str
            rule_id = str(data["rule_id"])  # stable str
            action = f"rule:{rule_id}"
            reason = f"Matched rule {rule_id}"
            confidence = 0.75
            item_id = self._compute_item_id(action=action, target=path, reason=reason)
            self.items[item_id] = PlanItemModel(
                id=item_id,
                action=action,
                target=path,
                reason=reason,
                confidence=confidence,
            )

        elif et == "CorrectionAdded":
            # No item-id scoping provided in current schema; bump generation.
            self.correction_gen += 1

        # ClustersFormed and others are ignored by this projection for v0.1.

    def current_plan(self) -> PlanModel:
        """Return the current deterministic plan with a stable id."""
        items = sorted(self.items.values(), key=lambda x: x.id)
        pid = self._compute_plan_id(items=items)
        return PlanModel(id=pid, items=items)

    def _compute_item_id(self, *, action: str, target: Path, reason: str) -> str:
        payload = {
            "action": action,
            "target": str(target),
            "reason": reason,
        }
        return compute_checksum("PlanItem", payload)

    def _compute_plan_id(self, *, items: List[PlanItemModel]) -> str:
        # Deterministic JSON payload for hashing.
        payload = {
            "version": 1,
            "correction_gen": self.correction_gen,
            "items": [
                {
                    "id": it.id,
                    "action": it.action,
                    "target": str(it.target),
                    "reason": it.reason,
                    "confidence": it.confidence,
                }
                for it in items
            ],
        }
        return compute_checksum("Plan", payload)
