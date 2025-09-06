"""ReviewerAgent stub.

Collects approvals/corrections (HITL)."""

from __future__ import annotations

from projections.plan_view import PlanView


class ReviewerAgent:
    def review(self, plan: PlanView) -> PlanView:
        # Stub: passthrough
        return plan

