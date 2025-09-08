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
from tools.tree_shaper import shape_cluster_moves


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
    root: Path | None = None

    def apply(self, event: EventRecord) -> None:
        """Apply a single event to update the plan state."""
        et = event.type
        data = event.data

        if et == "FilesScanned":
            # Track root for destination planning.
            try:
                self.root = Path(data.get("root")) if data.get("root") else None
            except Exception:
                self.root = None

        elif et == "RuleMatched":
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

        elif et == "ClustersFormed":
            # Merge clusters into create/move actions if assignments are provided.
            items = data.get("items") or []
            if not items or self.root is None:
                return
            # Group by cluster id, skip noise (-1)
            buckets: Dict[int, List[tuple[Path, float, str | None]]] = {}
            labels: Dict[int, str] = {}
            for it in items:
                cid = int(it.get("cluster_id", -1))
                if cid == -1:
                    continue
                try:
                    p = Path(it.get("path"))
                    conf = float(it.get("confidence", 0.5))
                    lbl = it.get("label")
                except Exception:
                    continue
                buckets.setdefault(cid, []).append((p, conf, lbl))
                if cid not in labels and lbl:
                    labels[cid] = str(lbl)

            # Create deterministic actions per cluster
            for cid in sorted(buckets.keys()):
                members = [p for (p, _c, _l) in buckets[cid]]
                # Fallback label if none provided
                label = labels.get(cid) or f"cluster-{cid}"
                dirs, moves = shape_cluster_moves(
                    root=self.root, label=label, members=members, max_depth=2, max_children=None
                )
                # Create directories (explicit create actions)
                for d in sorted(set(dirs)):
                    reason = f"cluster:{label}"
                    action = "create_dir"
                    item_id = self._compute_item_id(action=action, target=d, reason=reason)
                    self.items[item_id] = PlanItemModel(
                        id=item_id,
                        action=action,
                        target=d,
                        reason=reason,
                        confidence=0.6,
                    )
                # Moves for members
                # Average confidence for cluster used only for moves lacking explicit conf
                avg_conf = (
                    sum(c for (_p, c, _l) in buckets[cid]) / max(1, len(buckets[cid]))
                )
                for src, dst in moves:
                    reason = f"cluster:{label} from {src.name}"
                    action = "move"
                    conf = next((c for (p, c, _l) in buckets[cid] if p == src), avg_conf)
                    item_id = self._compute_item_id(action=action, target=dst, reason=reason)
                    self.items[item_id] = PlanItemModel(
                        id=item_id,
                        action=action,
                        target=dst,
                        reason=reason,
                        confidence=max(0.0, min(1.0, float(conf))),
                    )

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
