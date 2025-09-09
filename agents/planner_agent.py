"""PlannerAgent.

Coordinates deterministic planning steps from events:
- Replays the latest scan to collect candidate files
- Applies rules to emit ``RuleMatched`` events
- Optionally computes simple embeddings and clusters to emit ``ClustersFormed``
- Materializes the current plan and emits ``PlanProposed`` with item ids

The agent is offline by default and avoids any network calls.
"""

from __future__ import annotations

from pathlib import Path

from projections.base import replay
from projections.file_index import FileIndex
from projections.plan_view import PlanItem, PlanProjection, PlanView
from schemas import events as ev
from storage.event_store import EventStore
from tools import clustering as cl
from tools import embeddings as emb
from tools import rule_engine


class PlannerAgent:
    """Planner agent that emits events and returns a view for CLI display.

    The returned ``PlanView`` is a lightweight rendering convenience; the
    durable source of truth is the ``PlanProposed`` event and the underlying
    materialized plan (``PlanProjection``) that is reproducible from the event
    log.
    """

    def __init__(self, store: EventStore) -> None:
        self.store = store

    def _collect_files_from_events(self, *, root: Path) -> list[Path]:
        idx = FileIndex()
        replay(idx, self.store)
        # Prefer files under the provided root
        files: list[Path] = []
        for meta in idx.entries.values():
            try:
                if meta.is_dir:
                    continue
                # Ensure path is under root to avoid mixing multiple scans
                p = Path(meta.path)
                if root in p.parents or p == root:
                    files.append(p)
            except Exception:
                continue
        return files

    def propose_plan(
        self,
        *,
        root: Path,
        semantic: bool = False,
        rules_path: Path | None = None,
    ) -> PlanView:
        """Run rule matching and optional clustering, then emit PlanProposed.

        Args:
            root: Scan root already recorded by ``FilesScanned`` events.
            semantic: If True, computes simple embeddings and clusters.
            rules_path: Optional path to YAML/JSON rules file.

        Returns:
            A ``PlanView`` suitable for CLI display (non-durable).
        """
        root = root.resolve()

        # 1) Candidate files from the latest scan batches
        files = self._collect_files_from_events(root=root)

        # 2) Apply rules and emit RuleMatched events
        if rules_path is not None:
            try:
                rules = rule_engine.load_rules_from_yaml(rules_path)
                rule_engine.emit_rule_matches(files, rules, self.store)
            except Exception:
                # Keep planner resilient; continue without rule matches
                pass

        # 3) Optional embeddings + clustering
        if semantic and files:
            try:
                # Use deterministic fallback provider directly for vectors
                texts = [emb.prepare_text_for_file(p) for p in files]
                vectors = emb.FallbackProvider(dim=64).embed(texts)
                # Emit an informational embeddings event
                try:
                    self.store.append(ev.EmbeddingsComputed(count=len(vectors)))
                except Exception:
                    pass
                # Emit ClustersFormed with TF‑IDF labels over stems
                cl.cluster_vectors(
                    paths=files,
                    vectors=vectors,
                    store=self.store,
                    texts=[p.stem for p in files],
                    min_cluster_size=2,
                )
            except Exception:
                # Clustering is optional; ignore failures
                pass

        # 4) Materialize current plan deterministically and emit PlanProposed
        proj = PlanProjection()
        replay(proj, self.store)
        plan = proj.current_plan()
        try:
            self.store.append(
                ev.PlanProposed(plan_id=plan.id, item_ids=[it.id for it in plan.items])
            )
        except Exception:
            pass

        # 5) Return a thin view for display
        view_items = [
            PlanItem(
                id=it.id,
                action=it.action,
                target=it.target,
                reason=it.reason,
                confidence=it.confidence,
            )
            for it in plan.items
        ]
        return PlanView(items=view_items)
