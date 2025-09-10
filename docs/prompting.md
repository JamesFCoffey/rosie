# Prompting Guide for Codex on Rosie

This guide describes how to write effective, safe prompts for contributing to Rosie. It also summarizes the guardrails and output formats the project expects.


Core Principles

- Privacy: No outbound network calls. Use offline‑only approaches and pure functions.
- Safety: Dry‑run first; executor writes a checkpoint before mutation and supports undo. Avoid destructive defaults.
- Determinism: Projections and hashes must be reproducible from events. Prefer pure, typed functions with explicit inputs/outputs.
- Windows‑aware: Handle long paths, reparse points, OneDrive, cross‑volume moves, and Recycle Bin semantics.


Output Conventions

- When the task specifies “unified diff only”, return a single diff (no prose).
- When it specifies “full files only”, return the complete file contents (no extra commentary).
- Otherwise, keep responses concise with clear next steps.


Common Task Patterns

1) Implement a tool (pure function) under `tools/`:
   - Add type hints and docstrings.
   - If it emits domain state, define/extend an event in `schemas/events.py` and append via `storage/event_store.py`.
   - Add tests under `tests/` using temp dirs and no network.

2) Add/extend a projection under `projections/`:
   - Provide `.apply(event)` and validate replay determinism (same events → same hash/id/output).
   - Avoid filesystem or network I/O inside projections.

3) Wire orchestrator/agents:
   - Orchestrator (`core/graph.py`) should re‑run only affected nodes on `CorrectionAdded`.
   - PlannerAgent emits `PlanProposed`; ReviewerAgent emits `UserApproved`/`CorrectionAdded`; ExecutorAgent emits `ApplyStarted`/`ActionApplied` and uses `tools/checkpoint.py`.

4) Safety & Windows specifics:
   - Do not follow reparse points (`os_win/reparse_points.is_reparse_point`).
   - Skip hidden/system files by default in scanning.
   - Detect OneDrive paths (`os_win/onedrive.is_onedrive_path`) and reduce risk/confidence or require `--force` at apply.
   - Cross‑volume moves require copy+verify+delete; same‑volume use atomic rename.


Prompt Templates

Implement a tool + projection (diff only):

```
Implement tools/<name>.py to ...  
Update projections/<projection>.py to ...  
Wire <agent or CLI> to use it.  
Add tests for determinism and edge cases.  
Output: unified diff only.
```

Add an event + round‑trip tests:

```
Extend schemas/events.py with <EventName> (...) with to/from JSON helpers.  
Emit in <tool or agent>.  
Add tests for serialization round‑trip and projection replay.  
Output: unified diff only.
```

Docs refresh (full files):

```
Generate/replace docs: README.md (overview/safety/quickstart), docs/agents.md (Planner/Reviewer/Executor flow), docs/prompting.md (guardrails & cheat‑sheet).  
Output: full files only.
```


Testing Guidance

- Use `pytest` with `tmp_path` or `TemporaryDirectory` for filesystem fixtures.
- Avoid time‑sensitive or network‑dependent tests. Mock where necessary.
- For determinism, assert plan ids/hashes and projection output equality across replays.
- Use scriptable commands for the TUI (ReviewerAgent) to avoid interactive tests.


Do/Don’t Quick List

- Do: Keep functions small, typed, and pure; raise actionable errors; use structured logs (no prints in libraries).
- Do: Prefer pathlib.Path; guard Windows behaviors; include docstrings.
- Don’t: Add telemetry, network calls, or non‑deterministic behaviors; swallow exceptions silently; mutate global state.


References

- Orchestrator: `core/graph.py`
- Events: `schemas/events.py`
- Projections: `projections/*`
- Agents: `agents/*`
- Tools: `tools/*`

