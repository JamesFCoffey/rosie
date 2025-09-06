"""PlannerAgent stub.

Proposes a plan from scanning + rules + (optional) semantics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from projections.plan_view import PlanItem, PlanView


class PlannerAgent:
    def propose_plan(
        self,
        *,
        root: Path,
        semantic: bool = False,
        rules_path: Optional[Path] = None,
    ) -> PlanView:
        # Minimal placeholder: an informational item.
        return PlanView(
            items=[
                PlanItem(
                    id="plan-proposed",
                    action="info",
                    target=root,
                    reason="PlannerAgent stub proposed plan",
                    confidence=1.0,
                )
            ]
        )

