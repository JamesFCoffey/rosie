# Agents and Event Flow

This document explains how Rosie’s agents collaborate over the event‑sourced core to deliver a safe, auditable cleanup workflow.


Architecture Overview

- Orchestrator (`core/graph.py`): Coordinates tools and agents, replays events, and triggers incremental invalidation on corrections.
- Event Store (`storage/event_store.py`): SQLite append‑only log of domain events.
- Projections (`projections/*`): Deterministic materialized views built from events (Plan View, File Index, Embedding Cache, Checkpoint Log).
- Tools (`tools/*`): Pure, offline functions for scanning, rules, embeddings, clustering, shaping, conflict resolution, checkpointing, and file ops.
- Agents (`agents/*`): Planner, Reviewer (HITL), Executor.


Event Model (initial set)

- FilesScanned → RuleMatched → EmbeddingsComputed → ClustersFormed → PlanProposed → UserApproved/CorrectionAdded → PlanFinalized → ApplyStarted → ActionApplied → UndoPerformed

All events are JSON‑serializable Pydantic models with a stable `type` string.


PlannerAgent

- Location: `agents/planner_agent.py`
- Inputs: latest `FilesScanned` batches; optional rules file; `--semantic`; shaping limits (`--max-depth`, `--max-children`).
- Steps:
  1) Collect candidate files from `FileIndex`.
  2) Apply deterministic rules (`RuleMatched` events).
  3) Optional embeddings + clustering → `EmbeddingsComputed`, `ClustersFormed`.
  4) Materialize the current plan (`PlanProjection`) and emit `PlanProposed`.
- Output for CLI display: a `PlanView` with items (non‑durable convenience).


ReviewerAgent (HITL)

- Location: `agents/reviewer_agent.py`, TUI in `cli/tui.py`.
- Role: Collect approvals and corrections from the user.
- Emits:
  - `UserApproved` (list of approved item ids)
  - `CorrectionAdded` (free‑form notes like `reject:<id> ...`, `relabel:<id> ...`, `exclude:...`, `rule:{...}`)
- Orchestrator impact: `CorrectionAdded` triggers incremental invalidation and scoped recompute (rules/clusters as needed).


ExecutorAgent

- Location: `agents/executor_agent.py`
- Precondition: `PlanFinalized` for the plan id (CLI can also pass `--plan` to treat as explicit approval).
- Safety:
  - OneDrive guard (override with `--force`)
  - Max actions threshold
  - Max total move size threshold
  - Cross‑volume moves = copy + verify + delete; same‑volume = atomic rename
  - Deletes use Recycle Bin where supported
- Journaling:
  - Emits `ApplyStarted`
  - For each item, emits `ActionApplied`
  - Writes a checkpoint (`tools/checkpoint.py`) recording reversible actions
  - `undo` reads the checkpoint and replays in reverse; emits `UndoPerformed`


PlanProjection and Conflict Resolution

- Location: `projections/plan_view.py`
- Merges inputs:
  - `RuleMatched` → rule‑based informational or move/create suggestions
  - `ClustersFormed` → labeled cluster destinations via `tools/tree_shaper.shape_cluster_moves`
  - Shaping limits are included in the plan hash for determinism
- Conflict resolver (`tools/conflict_resolver.py`):
  - Deduplicates colliding `create_dir`/`move` targets by deterministic suffixing
  - Annotates risks (cross‑volume, OneDrive paths, potential locks) and adjusts confidence
  - Caller recomputes item ids after resolution for a stable plan hash


Embeddings & Clustering Backends

- Embeddings (offline): Rosie prepares simple, deterministic per‑file texts using filename tokens
  and a short content preview (`tools/embeddings.py`). A pure‑Python fallback provider produces
  stable numeric vectors without network access or model downloads.
- HDBSCAN (`hdbscan` extra): A density‑based algorithm that can discover clusters of variable
  density and shape while labeling outliers as noise (`-1`). Rosie prefers HDBSCAN when available
  because it naturally handles “miscellaneous” files that don’t belong to any group.
- Agglomerative (`scikit‑learn` extra): A hierarchical bottom‑up clustering approach that merges
  items into clusters. Rosie uses this as a fallback when HDBSCAN is unavailable or produces only
  noise; it provides predictable grouping with a bounded number of clusters.
- Pure‑Python fallback: When no clustering extras are installed, Rosie uses a cosine‑similarity
  threshold grouping to keep behavior fully offline.
- Cluster labels and shaping: After clustering, Rosie computes lightweight TF‑IDF labels over the
  names/snippets and then shapes target folders with `--max-depth`/`--max-children` constraints to
  integrate into the plan.



Incremental Invalidation

- Location: `core/graph.py`
- The orchestrator reads new events and updates in‑memory state:
  - `FilesScanned` → full invalidate
  - `CorrectionAdded` → path‑scoped invalidation (if a `path=...` hint is present), else full
- Only affected nodes rerun (rules → clusters) before projecting an updated plan id.


CLI Surface

- `scan` → plan preview + “Largest Folders” report; optional `--out plan.json`
- `apply --yes` → executes finalized plan with checkpointing
- `undo --checkpoint` → restores from journal
- `dev-clean` → lists or removes dev caches (via Recycle Bin on Windows)


FAQ

- Why event‑sourced?
  - Strong auditability, reproducible plans, targeted recomputation, natural path to GUI/API.
- Does Rosie require internet?
  - No. All models/tools are offline; default embedding provider is deterministic and local.
- Can I undo everything?
  - Actions recorded in the checkpoint are undoable; operations outside the journal are never attempted.
