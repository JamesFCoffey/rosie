# Rosie — local‑first cleanup maid (v0.1)

Rosie is a local‑first CLI “maid” that scans, proposes, and safely applies organization/cleanup actions on Windows. It combines deterministic rules with semantic clustering, all wrapped in an event‑sourced core so plans are auditable, reproducible, and undoable.

Privacy and safety are defaults: no network access; dry‑run planning; Windows‑aware file operations; checkpoints and undo.


Overview

- Event‑sourced pipeline: Scan → Rules → Embeddings → Clustering → Tree Shaping → Conflict Resolution → Plan Proposed → Review → Plan Finalized → Apply (Checkpoint) → Undo.
- Orchestrator + agents:
  - PlannerAgent builds a candidate plan (rules‑first with optional semantic clustering).
  - ReviewerAgent (Rich TUI) collects approvals/corrections as events.
  - ExecutorAgent performs Windows‑safe operations, with a checkpoint journal and undo.
- Projections (materialized views) keep current Plan, File Index, Embedding Cache, and Checkpoint Log in sync with events.
- No telemetry, no remote calls. Offline‑only.


Install

Requirements: Python 3.11+ on Windows (works cross‑platform for dry‑run/tests; Windows‑specific behaviors are no‑ops elsewhere).

1) Create/activate a virtualenv and install:

   # Minimal dev toolchain
   pip install -e .[dev]

   # With clustering backends (HDBSCAN + scikit‑learn)
   pip install -e .[dev,cluster]

2) Confirm CLI is available:

   python -m cli.main --help


Safety Defaults

- Dry‑run planning: `rosie scan` never mutates disk. It emits events and materializes a deterministic plan you can review.
- Checkpoints before apply: `rosie apply --yes` writes a journal (checkpoint) so you can undo.
- Windows‑aware operations: atomic rename when possible, cross‑volume copy+verify+delete, Recycle Bin deletes where supported, OneDrive guard.
- Sensible skips: system/hidden files are skipped by default; junctions/symlinks are not followed.


Quickstart

1) Scan a folder (dry‑run):

   python -m cli.main scan C:\\path\\to\\folder --rules rules.json --semantic --max-depth 2 --max-children 10 --out plan.json

   - Prints a proposed plan with reasons and confidences

   - Exports deterministic `plan.json` if `--out` is provided

   - Shows a “Largest Folders” summary to guide cleanup

2) Review and approvals (HITL):

   - Current v0.1 includes a scriptable TUI. Approvals/corrections are recorded as events (`UserApproved`, `CorrectionAdded`).

   - Corrections re‑run only affected parts of the pipeline (incremental replay).

3) Apply (explicit confirmation required):

   python -m cli.main apply --yes

   - Requires an approved plan (either finalize via events or pass an explicit `--plan` JSON).

   - Writes a checkpoint journal with every action.

   - Enforces safety thresholds (max actions, total move size) and OneDrive guard (override with `--force`).

4) Undo:

   python -m cli.main undo --checkpoint C:\\Users\\you\\.rosie\\checkpoints\\20240101-abcdef.json

   - Replays the checkpoint in reverse; idempotent and best‑effort.


Dev‑Clean

List and optionally remove common development caches (dry‑run by default):

  python -m cli.main dev-clean C:\\projects\\repo --preset node --dry-run

  python -m cli.main dev-clean C:\\projects\\repo --apply

Presets: `all`, `node`, `python`, `docker`.


Command Reference

- Scan:

  python -m cli.main scan <path> [--rules FILE] [--semantic] [--max-depth N] [--max-children M] [--include …] [--exclude …] [--out plan.json] [--limit 20]

- Apply:

  python -m cli.main apply [--plan plan.json] [--checkpoint checkpoint.json] [--yes] [--force]

- Undo:

  python -m cli.main undo --checkpoint checkpoint.json

- Dev‑clean:

  python -m cli.main dev-clean <path> [--preset node|python|docker|all] [--dry-run|--apply]


Architecture (Brief)

- Event Store: SQLite append‑only log under `~/.rosie/rosie.db`.
- Projections: reconstruct Plan/File Index/Embed Cache/Checkpoint Log from events deterministically.
- Agents: Planner/Reviewer/Executor act on projections and persist decisions via events.
- Tools: pure functions for scanning, rules, embeddings, clustering, shaping, conflicts, checkpoints, file ops.

See docs/agents.md for a deeper dive.


Privacy

- No outbound network calls; offline models only.
- All data stays local; plans/checkpoints are machine‑readable JSON.


Contributing

Run tests:

  pytest -q

Lint/type/format:

  ruff check .
  mypy .
  black --check .

Guardrails for contributions are in docs/prompting.md.


Clustering Backends (Optional)

Rosie can group related files using unsupervised clustering over simple, local embeddings.

- HDBSCAN (from the `hdbscan` library): a density‑based clustering algorithm that
  automatically finds clusters of varying shape and marks outliers as noise (`-1`).
  It works well for heterogeneous file sets where some files do not belong to any group.
- Agglomerative clustering (from `scikit‑learn`): a hierarchical linkage method that
  merges items bottom‑up until the desired number of clusters is formed. It’s a dependable
  fallback when density‑based methods aren’t available or produce all‑noise results.

How Rosie uses them:

- Embeddings: Rosie builds simple, deterministic text features using filename tokens and a small
  preview of file contents (tools/embeddings.py fallback provider). No network or model downloads
  are required.
- Clustering: If you install the optional extras (`pip install -e .[cluster]`), Rosie prefers
  HDBSCAN. If that’s not available or yields only noise, it falls back to agglomerative; if both
  are unavailable, Rosie uses a pure‑Python cosine‑similarity grouping.
- Labels and shaping: Clusters are labeled heuristically (TF‑IDF over names/snippets) and shaped
  into a folder structure respecting `--max-depth`/`--max-children`, then merged into the plan.
