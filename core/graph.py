"""Async orchestrator skeleton for Rosie.

Coordinates agents and tools, writes events, and materializes projections.
This skeleton uses in-memory stubs to enable CLI flows without side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import structlog

from projections.plan_view import PlanItem, PlanView
from storage.event_store import EventStore
from tools import dev_clean as dev_clean_tool
from tools import file_scanner

logger = structlog.get_logger(__name__)


@dataclass
class ApplyResult:
    summary: str


@dataclass
class UndoResult:
    summary: str


@dataclass
class DevCleanItem:
    path: Path
    size_mb: float
    action: str


@dataclass
class DevCleanReport:
    items: list[DevCleanItem]


class Orchestrator:
    """LangGraph-compatible orchestrator skeleton.

    Args:
        db_path: Path to event store (unused in stub; kept for API)
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.events = EventStore(self.db_path)

    def scan_and_plan(
        self,
        *,
        root: Path,
        rules_path: Optional[Path],
        semantic: bool,
        max_depth: Optional[int],
        max_children: Optional[int],
        include: Optional[str],
        exclude: Optional[str],
    ) -> PlanView:
        """Scan the filesystem and build a dry-run plan view.

        Returns a minimal plan with no mutating actions (safe preview).
        """
        root = root.resolve()
        files = list(self._safe_scan(root=root, include=include, exclude=exclude))
        # Create a single informational item summarizing the scan.
        item = PlanItem(
            id="scan-summary",
            action="info",
            target=root,
            reason=f"Scanned {len(files)} items under {root}",
            confidence=1.0,
        )
        return PlanView(items=[item])

    def apply(self, *, plan_path: Optional[Path], checkpoint_path: Optional[Path]) -> ApplyResult:
        """Apply an approved plan.

        Stub implementation only logs intent and returns summary.
        """
        msg = "Apply called (stub). No changes made."
        logger.info("apply_called", plan_path=str(plan_path) if plan_path else None)
        return ApplyResult(summary=msg)

    def undo(self, *, checkpoint_path: Path) -> UndoResult:
        """Undo a checkpointed apply.

        Stub implementation returns summary only.
        """
        msg = f"Undo called for {checkpoint_path} (stub)."
        logger.info("undo_called", checkpoint_path=str(checkpoint_path))
        return UndoResult(summary=msg)

    def dev_clean(self, *, path: Path, preset: str, dry_run: bool) -> DevCleanReport:
        """List and optionally remove common dev caches.

        This is safe: for now it only reports findings; deletion is not implemented.
        """
        findings = dev_clean_tool.find_dev_caches(path, preset=preset)
        items = [
            DevCleanItem(path=f.path, size_mb=f.size_mb, action=("delete" if not dry_run else "keep"))
            for f in findings
        ]
        return DevCleanReport(items=items)

    def _safe_scan(
        self, *, root: Path, include: Optional[str], exclude: Optional[str]
    ) -> Iterable[Path]:
        patterns_include = [p.strip() for p in include.split(",") if p.strip()] if include else []
        patterns_exclude = [p.strip() for p in exclude.split(",") if p.strip()] if exclude else []
        return file_scanner.scan_paths(root=root, include=patterns_include, exclude=patterns_exclude)

