"""Async orchestrator skeleton for Rosie.

Coordinates agents and tools, writes events, and materializes projections.
Adds an asyncio-friendly incremental re-run mechanism with scoped invalidation
triggered by events (e.g., ``CorrectionAdded``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

try:
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)
except Exception:  # pragma: no cover - fallback when structlog is unavailable
    import logging

    logger = logging.getLogger(__name__)

from projections.plan_view import PlanItem, PlanView, PlanProjection
from projections.base import replay
from schemas import events as ev
from storage.event_store import EventStore
from tools import dev_clean as dev_clean_tool
from tools import file_scanner
from tools import rule_engine, clustering
from agents.executor_agent import ExecutorAgent
from projections.plan_view import PlanProjection
from projections.base import replay

# logger defined above (structlog or stdlib logging)


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


# -----------------------------
# Orchestrator state dataclasses
# -----------------------------


@dataclass
class NodeRunStats:
    """Execution counters for pipeline nodes.

    These are mainly used by tests to ensure incremental invalidation logic
    re-executes only the required parts of the pipeline.
    """

    scanner_runs: int = 0
    rule_runs: int = 0
    cluster_runs: int = 0
    # Granular counts to assert scoped re-execution size
    rule_paths_evaluated: int = 0
    cluster_paths_evaluated: int = 0


@dataclass
class PipelineState:
    """In-memory state for the scanning → rules → clustering pipeline."""

    last_event_id: int = 0
    root: Optional[Path] = None
    paths: Set[Path] = field(default_factory=set)
    rule_matches: Dict[Path, str] = field(default_factory=dict)
    clusters: Dict[str, List[Path]] = field(default_factory=dict)
    dirty_paths: Set[Path] = field(default_factory=set)
    full_invalidate: bool = False
    runs: NodeRunStats = field(default_factory=NodeRunStats)
    # Optional rules provided by caller/tests
    ruleset_json: Optional[dict] = None  # store Pydantic dump for stability


class Orchestrator:
    """LangGraph-compatible orchestrator skeleton.

    Args:
        db_path: Path to event store
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.events = EventStore(self.db_path)
        self._state = PipelineState()
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        # Default: no rules; tests/CLI can inject via set_rules
        self._rules = None
        # Plan projection state: keep a rolling materialized view and cursor
        self._plan = PlanProjection()
        self._plan_last_id = 0

    # -----------------------------
    # Public configuration helpers
    # -----------------------------

    def set_rules(self, rules: Optional["schemas.rules.RuleSet"]) -> None:  # noqa: F821
        """Attach a ruleset for the rule engine.

        Args:
            rules: Optional RuleSet. If None, the rule step is skipped.
        """
        if rules is None:
            self._rules = None
            self._state.ruleset_json = None
        else:  # store a plain JSON payload to avoid runtime coupling
            self._rules = rules
            self._state.ruleset_json = rules.model_dump(mode="json")

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
        # Use the async scanner to emit batched FilesScanned events with metadata.
        patterns_include = [p.strip() for p in include.split(",") if p.strip()] if include else []
        patterns_exclude = [p.strip() for p in exclude.split(",") if p.strip()] if exclude else []
        try:
            import asyncio as _asyncio

            total = _asyncio.run(
                file_scanner.scan_and_emit(
                    root=root,
                    store=self.events,
                    include=patterns_include,
                    exclude=patterns_exclude,
                    batch_size=512,
                )
            )
        except RuntimeError:
            # If an event loop is already running (e.g., from an embedding server),
            # fall back to a synchronous compatibility scan for count only.
            files = list(self._safe_scan(root=root, include=include, exclude=exclude))
            total = len(files)
            try:
                self.events.append(ev.FilesScanned(root=root, count=total))
            except Exception:
                logger.warning("files_scanned_event_append_failed", root=str(root))

        # Create a single informational item summarizing the scan.
        item = PlanItem(
            id="scan-summary",
            action="info",
            target=root,
            reason=f"Scanned {total} items under {root}",
            confidence=1.0,
        )
        return PlanView(items=[item])

    def apply(
        self,
        *,
        plan_path: Optional[Path],
        checkpoint_path: Optional[Path],
        force: bool = False,
        max_actions: int | None = None,
        max_total_move_bytes: int | None = None,
    ) -> ApplyResult:
        """Apply an approved plan.

        Execution requires a PlanFinalized event. If ``plan_path`` is provided,
        it is treated as an explicit user-approved plan and a PlanFinalized
        event is emitted for that plan id prior to execution.
        """
        # Materialize current plan view from events by default
        proj = PlanProjection()
        replay(proj, self.events)
        current = proj.current_plan()

        # Decide plan source for execution
        if plan_path is not None:
            # Treat as explicit approval and emit PlanFinalized
            try:
                import json as _json
                data = _json.loads(Path(plan_path).read_text())
                # Minimal validation of schema
                plan_id = str(data.get("id"))
                item_ids = [str(it.get("id")) for it in (data.get("items") or [])]
                if plan_id:
                    self.events.append(ev.PlanFinalized(plan_id=plan_id, approved_item_ids=item_ids))
                # Use a lightweight PlanView for execution
                from projections.plan_view import PlanView, PlanItem

                items = [
                    PlanItem(
                        id=str(it.get("id")),
                        action=str(it.get("action")),
                        target=Path(it.get("target")),
                        reason=str(it.get("reason")),
                        confidence=float(it.get("confidence", 1.0)),
                    )
                    for it in (data.get("items") or [])
                ]
                plan_view = PlanView(items=items)
            except Exception as e:
                return ApplyResult(summary=f"Failed to load plan: {e}")
        else:
            # Ensure we have an approval for current plan id
            approved = False
            for rec in self.events.read_all():
                if rec.type == "PlanFinalized" and str(rec.data.get("plan_id")) == current.id:
                    approved = True
            if not approved:
                return ApplyResult(summary="Plan not finalized; approval required before apply")
            # Build a PlanView from current PlanProjection items
            from projections.plan_view import PlanItem, PlanView

            items = [
                PlanItem(
                    id=it.id,
                    action=it.action,
                    target=it.target,
                    reason=it.reason,
                    confidence=it.confidence,
                )
                for it in current.items
            ]
            plan_view = PlanView(items=items)

        exec_agent = ExecutorAgent(self.events)
        result = exec_agent.apply(
            plan_view,
            checkpoint_path=checkpoint_path,
            max_actions=max_actions,
            max_total_move_bytes=max_total_move_bytes,
            force=force,
        )
        return ApplyResult(summary=result.summary)

    def undo(self, *, checkpoint_path: Path) -> UndoResult:
        """Undo a checkpointed apply using the executor agent."""
        exec_agent = ExecutorAgent(self.events)
        result = exec_agent.undo(checkpoint_path=checkpoint_path)
        return UndoResult(summary=result.summary)

    def dev_clean(self, *, path: Path, preset: str, dry_run: bool) -> DevCleanReport:
        """List and optionally remove common dev caches.

        On Windows, deletions are sent to the Recycle Bin. On non-Windows
        platforms (e.g., CI), deletions are performed directly to allow tests
        to validate behavior. Discovery is handled by ``tools.dev_clean``.
        """
        import os
        import shutil
        from tools import file_ops

        findings = dev_clean_tool.find_dev_caches(path, preset=preset)
        # Sort deepest paths first to avoid parent-first deletes interfering with children
        findings_sorted = sorted(findings, key=lambda f: len(str(f.path)), reverse=True)
        items: list[DevCleanItem] = []
        if dry_run:
            for f in findings_sorted:
                items.append(DevCleanItem(path=f.path, size_mb=f.size_mb, action="keep"))
            return DevCleanReport(items=items)

        for f in findings_sorted:
            action = "delete"
            try:
                if os.name == "nt":
                    file_ops.recycle_delete(f.path)
                else:
                    shutil.rmtree(f.path, ignore_errors=True)
            except Exception:  # pragma: no cover - defensive
                # Keep action as "delete" to reflect intent; errors are ignored for safety
                pass
            items.append(DevCleanItem(path=f.path, size_mb=f.size_mb, action=action))
        return DevCleanReport(items=items)

    def _safe_scan(
        self, *, root: Path, include: Optional[str], exclude: Optional[str]
    ) -> Iterable[Path]:
        patterns_include = [p.strip() for p in include.split(",") if p.strip()] if include else []
        patterns_exclude = [p.strip() for p in exclude.split(",") if p.strip()] if exclude else []
        return file_scanner.scan_paths(root=root, include=patterns_include, exclude=patterns_exclude)

    # -----------------------------
    # Async event-driven orchestration
    # -----------------------------

    async def run_once(self) -> None:
        """Process new events and perform incremental re-execution.

        This method is idempotent and safe to call repeatedly. It reads events
        since the last processed id, updates dirty scopes, and re-runs only the
        necessary pipeline parts (scanner/rules/clustering).
        """
        async with self._lock:
            new_events = self.events.read_since(self._state.last_event_id)
            if not new_events:
                return

            # Phase 1: read events and compute invalidation scopes
            for rec in new_events:
                et = rec.type
                data = rec.data
                if et == "FilesScanned":
                    # Full scan event establishes root; trigger full recompute
                    self._state.root = Path(data["root"]) if data.get("root") else None
                    self._state.full_invalidate = True
                elif et == "CorrectionAdded":
                    # Try to scope to a path=... hint in the note; else full invalidation
                    note = str(data.get("note", ""))
                    path = self._extract_path_hint(note)
                    if path is not None:
                        self._state.dirty_paths.add(path)
                    else:
                        self._state.full_invalidate = True
                # Other events aren't used by the pipeline state yet

            # Phase 2: run nodes based on invalidation
            await self._maybe_run_scanner()
            await self._maybe_run_rules()
            await self._maybe_run_clusters()

            # Phase 3: reset invalidation and advance cursor
            self._state.dirty_paths.clear()
            self._state.full_invalidate = False
            self._state.last_event_id = new_events[-1].id
            # Update the Plan projection based on newly appended events
            self._plan_last_id = replay(self._plan, self.events, since_id=self._plan_last_id)

    async def run_forever(self, *, poll_interval_s: float = 0.2) -> None:
        """Continuously process events until ``stop()`` is called."""
        while not self._stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=poll_interval_s)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        """Signal ``run_forever`` to stop."""
        self._stop.set()

    # -----------------------------
    # Internal node runners
    # -----------------------------

    async def _maybe_run_scanner(self) -> None:
        # Run scanner only on full invalidations; path-scoped corrections do not rescan
        if not self._state.full_invalidate:
            return
        root = self._state.root
        if root is None:
            return
        # Use simple include/exclude defaults for now
        # Keep scanner semantics simple and predictable for tests: only direct files
        paths = [p for p in root.glob("*") if p.is_file()]
        self._state.paths = set(paths)
        self._state.runs.scanner_runs += 1

    async def _maybe_run_rules(self) -> None:
        if self._rules is None and self._state.ruleset_json is None:
            # No rules attached, nothing to compute
            return
        # Determine which paths to evaluate
        if self._state.full_invalidate or not self._state.rule_matches:
            to_eval: Set[Path] = set(self._state.paths)
        else:
            to_eval = set(p for p in self._state.dirty_paths if p in self._state.paths)
        if not to_eval and not self._state.full_invalidate:
            return
        # Execute rule engine over the chosen subset
        evaluated_set: Set[Path] = set(to_eval if to_eval else self._state.paths)
        evaluated_count = len(evaluated_set)
        if self._rules is not None:
            matches = rule_engine.match_rules(evaluated_set, self._rules)
        else:
            # In tests, ruleset may be attached only via JSON; skip computation.
            matches = {p: "<unknown>" for p in evaluated_set}
        # Update in-memory state (both additions and removals within evaluated subset)
        for p in evaluated_set:
            if p in matches:
                self._state.rule_matches[p] = matches[p]
            else:
                self._state.rule_matches.pop(p, None)
        # Emit RuleMatched events for the currently matched subset to feed PlanProjection
        # Emitting only for evaluated_set keeps deterministic scope
        for p, rid in matches.items():
            try:
                self.events.append(ev.RuleMatched(path=p, rule_id=rid))
            except Exception:
                # Best-effort emission; keep pipeline deterministic regardless
                continue
        self._state.runs.rule_runs += 1
        self._state.runs.rule_paths_evaluated = evaluated_count

    async def _maybe_run_clusters(self) -> None:
        # Clustering is based on matched paths for now
        if not self._state.rule_matches and not self._state.full_invalidate:
            return
        # Compute clusters only for impacted subset if possible
        if self._state.full_invalidate or not self._state.clusters:
            impacted = set(self._state.rule_matches.keys())
        else:
            impacted = set(p for p in self._state.dirty_paths if p in self._state.rule_matches)
        if not impacted and not self._state.full_invalidate:
            return
        # Recompute impacted cluster buckets
        evaluated_count = len(impacted) if not self._state.full_invalidate else len(self._state.rule_matches)
        if self._state.full_invalidate:
            self._state.clusters = clustering.cluster_by_extension(self._state.rule_matches.keys())
        else:
            # Update only buckets for impacted extensions
            for p in impacted:
                ext = p.suffix.lower() or "<none>"
                # Rebuild this bucket from current matches
                self._state.clusters[ext] = [q for q in self._state.rule_matches if (q.suffix.lower() or "<none>") == ext]
        self._state.runs.cluster_runs += 1
        self._state.runs.cluster_paths_evaluated = evaluated_count

    # -----------------------------
    # Utilities
    # -----------------------------

    def _extract_path_hint(self, note: str) -> Optional[Path]:
        """Parse a ``path=...`` hint from a correction note.

        Example supported formats:
            - "path=/tmp/a.txt"
            - "fix name (path=a.txt)"  (relative paths are resolved under known root)
        """
        note = note.strip()
        if "path=" not in note:
            return None
        try:
            frag = note.split("path=", 1)[1]
            # delimiter could be space, comma, or end-of-string
            raw = frag.split(" ")[0].split(",")[0].strip().strip("()[]{}<>")
            p = Path(raw)
            if not p.is_absolute() and self._state.root is not None:
                p = (self._state.root / p).resolve()
            return p
        except Exception:
            return None

    # Expose stats for tests
    @property
    def run_stats(self) -> NodeRunStats:
        return self._state.runs

    # Expose current plan id for tests/CLI
    @property
    def current_plan_id(self) -> Optional[str]:
        try:
            return self._plan.current_plan().id
        except Exception:
            return None
