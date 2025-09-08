"""ReviewerAgent with HITL wiring.

Collects approvals/corrections (HITL) and emits ``UserApproved`` and
``CorrectionAdded`` events. Designed to work with a simple Rich TUI as well as
scripted test inputs.
"""

from __future__ import annotations

from typing import Iterable, Optional

from projections.base import replay
from projections.plan_view import PlanProjection, PlanView
from schemas import events as ev
from storage.event_store import EventStore
from cli.tui import ReviewResult, run_review


class ReviewerAgent:
    """Human-in-the-loop reviewer that persists decisions as events."""

    def __init__(self, store: EventStore) -> None:
        self.store = store

    def _current_plan_id(self) -> str:
        proj = PlanProjection()
        replay(proj, self.store)
        return proj.current_plan().id

    def review(
        self,
        plan: PlanView,
        *,
        commands: Optional[Iterable[str]] = None,
    ) -> ReviewResult:
        """Run a review session and emit events.

        Args:
            plan: The current plan view to review.
            commands: Optional scripted commands (for tests/non-interactive).

        Returns:
            ReviewResult: Summary of approved items and corrections recorded.
        """
        # Determine current plan id from projections to ensure determinism
        plan_id = self._current_plan_id()

        # Run the TUI/session (interactive or scripted)
        result = run_review(plan.items, commands=commands)

        # Emit events reflecting the user's decisions
        if result.approved_item_ids:
            try:
                self.store.append(
                    ev.UserApproved(plan_id=plan_id, item_ids=list(result.approved_item_ids))
                )
            except Exception:
                pass
        for note in result.corrections:
            try:
                self.store.append(ev.CorrectionAdded(plan_id=plan_id, note=note))
            except Exception:
                pass

        return result
