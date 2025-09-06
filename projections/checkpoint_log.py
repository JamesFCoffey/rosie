"""Checkpoint log projection.

Maintains an ordered log of actions applied during execution to support undo.
The log is deterministic: it only reflects data from events and preserves the
event order as read from the event store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from storage.event_store import EventRecord


@dataclass
class AppliedAction:
    item_id: str
    status: str
    message: Optional[str]


@dataclass
class CheckpointLog:
    """Materialized view for checkpoint/undo information."""

    current_plan_id: Optional[str] = None
    actions: List[AppliedAction] = field(default_factory=list)
    last_checkpoint_path: Optional[Path] = None

    def apply(self, event: EventRecord) -> None:
        et = event.type
        data = event.data
        if et == "ApplyStarted":
            # Begin a new apply session for a plan
            self.current_plan_id = str(data["plan_id"]) if "plan_id" in data else None
            self.actions.clear()
        elif et == "ActionApplied":
            self.actions.append(
                AppliedAction(
                    item_id=str(data["item_id"]),
                    status=str(data["status"]),
                    message=(str(data["message"]) if data.get("message") is not None else None),
                )
            )
        elif et == "UndoPerformed":
            p = Path(data["checkpoint_path"])  # Path serialized to string
            self.last_checkpoint_path = p
