**Project Overview**
- Purpose: Rosie is a local‑first CLI “maid” that scans, proposes, and safely applies organization/cleanup actions on Windows. It combines deterministic rules with semantic clustering, and always defaults to privacy and dry‑run safety.
- Architecture Choice: Option 3 — Event‑Sourced Core + Agent‑Orchestrated Pipelines.
  - Orchestrator: `core/graph.py` (LangGraph‑compatible) coordinates nodes and agents.
  - Event Store: `storage/event_store.py` (SQLite, append‑only) as the durable source of truth.
  - Projections/Views: Materialized views over events (e.g., Plan View, File Index, Embedding Cache). Stubs will live under `projections/`.
  - Agents: `agents/` contains Planner, Reviewer (HITL), and Executor that mediate between algorithms and user approvals.
  - Tools: `tools/` holds pure functions/utilities (scanner, rules, embeddings, clustering, tree shaping, conflicts, checkpoints, dev‑clean).
  - CLI: `cli/main.py` (Typer/Rich). Optional FastAPI can come later using the same event APIs.
- Privacy: No network by default, offline models only; telemetry off.
- Safety: Dry‑run by default, journaling checkpoints, Windows‑aware file ops.

**High‑Level Data Flow**
- Scan → Rules → Embeddings → Clustering → Tree Shaping → Conflict Resolution → Plan Proposed → Review (HITL) → Plan Finalized → Apply (Checkpoint) → Undo.
- Agents convert user input (approvals/corrections) into events that selectively re‑run parts of the pipeline.

**ASCII Diagram**
```
Typer CLI (Rich TUI)
  └── core/graph.py (Agent Orchestrator; LangGraph‑ready)
        ├── tools/file_scanner.py → schemas/events.py (FilesScanned)
        ├── tools/rule_engine.py  → (RuleMatched)
        ├── tools/embeddings.py   → tools/clustering.py → (ClustersFormed)
        ├── tools/tree_shaper.py  → tools/conflict_resolver.py
        ├── agents/planner_agent.py → (PlanProposed)
        ├── agents/reviewer_agent.py ↔ user → (UserApproved/CorrectionAdded)
        └── agents/executor_agent.py → tools/checkpoint.py → (ApplyStarted/ActionApplied)

storage/event_store.py (SQLite) ⇄ projections/* (Plan View, File Index, Embed Cache)
```

**Repository Layout**
- `cli/main.py`: Typer commands (`scan`, `apply`, `undo`, `dev-clean`).
- `core/graph.py`: Orchestrator skeleton (LangGraph‑compatible).
- `agents/`: Planner, Reviewer (HITL), Executor.
- `tools/`: Scanner, rule engine, embeddings, clustering, tree shaper, conflict resolver, checkpoint, dev‑clean.
- `storage/event_store.py`: Append‑only event store (SQLite WAL).
- `schemas/`: Events, Plan, Rules, Checkpoint dataclasses.
- `os_win/`: Windows adapters (long paths, reparse points, OneDrive, recycle bin) — to be implemented.
- `projections/`: Materialized views over events (e.g., `plan_view.py`) — to be implemented.

**How to Contribute (Agent Quickstart)**
- Run CLI locally: `python -m cli.main --help`
- Implement a tool:
  - Add a pure function in `tools/` with clear inputs/outputs and type hints.
  - If it emits domain state, define/extend an event in `schemas/events.py` and append via `storage/event_store.py`.
  - If it needs a view, add a projection under `projections/` that builds from events.
- Wire into the orchestrator:
  - Call your tool from `core/graph.py` (or the relevant agent) and emit events.
  - Keep any long‑running work `async`‑friendly; batch filesystem and CPU work.
- Human‑in‑the‑loop (HITL):
  - Reviewer collects approvals/corrections and writes `UserApproved` / `CorrectionAdded` events.
  - Orchestrator re‑invokes only affected steps (incremental re‑plan).
- Safety:
  - Dry‑run by default; executor must write a checkpoint before mutating disk and support undo.
  - Use Windows‑aware paths and avoid following reparse points unless explicitly allowed.

**Code Style Guidelines (Google Python Style)**
- Typing: Use explicit type hints everywhere; prefer `dataclasses` for simple records.
- Docstrings: Triple‑quoted, Google style sections (Args, Returns, Raises, Example).
- Imports: Standard library, third‑party, local — in that order; absolute imports.
- Naming: `snake_case` for functions/variables, `CamelCase` for classes, constants `UPPER_SNAKE`.
- Line length: 100 chars max; wrap thoughtfully.
- Errors: Raise specific exceptions; include actionable messages; never swallow exceptions silently.
- Logging: Use structured logs; no print in library code (CLI handles user output via Rich/Typer).
- Functions: Small and focused; avoid side effects; return data rather than mutate globals.
- Tests: Pytest with temporary directories; avoid network and time‑dependent flakiness.

**Testing & CI**
- Goal: >85% coverage on core modules.
- Unit tests for: scanner, rules, embeddings cache, clustering, plan merge, executor dry‑run.
- Use `tmp_path`/`TemporaryDirectory` for filesystem fixtures; simulate Windows paths/edge cases.
- CI: GitHub Actions later; tests must pass offline.

**Privacy & Safety Defaults**
- No outbound network calls; offline models only.
- Dry‑run is the default mode; `apply` requires explicit confirmation (`--yes`) and writes a checkpoint.
- Skip system/hidden folders unless explicitly allowed; OneDrive/long‑path guarded.

**Events (Initial Set)**
- `FilesScanned`, `RuleMatched`, `EmbeddingsComputed`, `ClustersFormed`, `PlanProposed`,
  `UserApproved`, `CorrectionAdded`, `PlanFinalized`, `ApplyStarted`, `ActionApplied`, `UndoPerformed`.

**CLI Surface (v0.1)**
- `rosie scan <path> [--rules FILE] [--semantic] [--max-depth N] [--max-children M] [--include …] [--exclude …] [--out plan.json]`
- `rosie apply --plan plan.json [--checkpoint checkpoint.json] [--yes]`
- `rosie undo --checkpoint checkpoint.json`
- `rosie dev-clean <path> [--preset node|python|docker|all] [--dry-run|--apply]`

**Development Notes**
- Python 3.11; prefer `pathlib.Path` and `blake3` for hashing (when added).
- Asynchrony: Use `asyncio` for scanning/IO; avoid blocking calls in the CLI path.
- Windows specifics: handle long paths, junctions/symlinks, cross‑volume moves (copy+verify+delete), recycle bin for deletes.

**Definition of Done (v0.1)**
- Dry‑run planning with reasons/confidence, reviewable via CLI TUI; checkpoints and undo work reliably; tests green with coverage target met; no network access; commands documented in this file.

