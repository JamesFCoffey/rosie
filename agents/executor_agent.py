"""ExecutorAgent stub.

Applies approved actions with checkpointing (not implemented)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from projections.plan_view import PlanView


@dataclass
class ExecutionResult:
    applied: int
    skipped: int
    summary: str


class ExecutorAgent:
    def apply(self, plan: PlanView, *, checkpoint_path: Path | None) -> ExecutionResult:
        return ExecutionResult(applied=0, skipped=len(plan.items), summary="Executor stub: no changes")

