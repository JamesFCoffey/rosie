"""Rosie CLI entrypoint.

Commands:
- scan: build a dry-run plan and optionally export JSON
- apply: apply an approved plan with checkpointing (requires --yes)
- undo: undo a previous checkpoint
- dev-clean: list and optionally remove common dev caches

This is a lightweight skeleton wired to the event store and orchestrator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from core.graph import Orchestrator
from agents.planner_agent import PlannerAgent
from projections.plan_view import PlanProjection
from projections.base import replay
from projections.file_index import FileIndex

app = typer.Typer(add_completion=False, help="Rosie — local-first cleanup maid (dry-run by default)")
console = Console()


def default_db_path() -> Path:
    """Return the default path to the Rosie SQLite event store.

    Returns:
        Path: Path to `~/.rosie/rosie.db`.
    """
    base = Path.home() / ".rosie"
    base.mkdir(parents=True, exist_ok=True)
    return base / "rosie.db"


@app.command()
def scan(
    path: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True, help="Root path"),
    rules: Optional[Path] = typer.Option(None, "--rules", help="YAML rules file"),
    semantic: bool = typer.Option(False, "--semantic", help="Enable embeddings+clustering"),
    max_depth: Optional[int] = typer.Option(None, "--max-depth", min=1),
    max_children: Optional[int] = typer.Option(None, "--max-children", min=1),
    include: Optional[str] = typer.Option(None, "--include", help="Comma-separated globs to include"),
    exclude: Optional[str] = typer.Option(None, "--exclude", help="Comma-separated globs to exclude"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write plan JSON to file"),
    limit: int = typer.Option(20, "--limit", min=1, help="Summary limit for display"),
    db: Optional[Path] = typer.Option(None, "--db", help="Path to event store DB"),
):
    """Scan path and produce a dry-run plan.

    This is a placeholder that records a FilesScanned event and materializes a minimal plan view.
    """
    orchestrator = Orchestrator(db_path=db or default_db_path())

    console.log("Starting scan (dry-run)…")
    # First, perform a filesystem scan and emit FilesScanned batches
    _scan_view = orchestrator.scan_and_plan(
        root=path,
        rules_path=rules,
        semantic=semantic,
        max_depth=max_depth,
        max_children=max_children,
        include=include,
        exclude=exclude,
    )
    # Then, run the planner over emitted events
    planner = PlannerAgent(orchestrator.events)
    planner.propose_plan(root=path, semantic=semantic, rules_path=rules)

    # Materialize the current deterministic plan for display/export
    proj = PlanProjection()
    replay(proj, orchestrator.events)
    plan = proj.current_plan()

    table = Table(title=f"Proposed Plan (dry-run) — id {plan.id}")
    table.add_column("Action ID")
    table.add_column("Action")
    table.add_column("Target")
    table.add_column("Reason")
    table.add_column("Confidence")
    for item in plan.items:
        table.add_row(item.id, item.action, str(item.target), item.reason, f"{item.confidence:.2f}")
    console.print(table)

    # Largest folders preview (if scan emitted batched metadata)
    idx = FileIndex()
    replay(idx, orchestrator.events)
    top = idx.largest_folders(limit=limit)
    if top:
        folders = Table(title=f"Largest Folders (top {limit})")
        folders.add_column("Folder")
        folders.add_column("Size (MB)", justify="right")
        for path, size in top:
            folders.add_row(str(path), f"{size / (1024*1024):.2f}")
        console.print(folders)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan.model_dump(mode="json"), indent=2))
        console.log(f"Wrote plan JSON to {out}")


@app.command()
def apply(
    plan: Optional[Path] = typer.Option(None, "--plan", help="Plan JSON to apply"),
    checkpoint: Optional[Path] = typer.Option(None, "--checkpoint", help="Checkpoint output path"),
    yes: bool = typer.Option(False, "--yes", help="Confirm execution; otherwise dry-run only"),
    db: Optional[Path] = typer.Option(None, "--db", help="Path to event store DB"),
):
    """Apply an approved plan using Windows-safe operations.

    Requires --yes to mutate disk. Without --yes, prints a reminder and exits non-zero.
    """
    if not yes:
        console.print("[yellow]Refusing to apply without --yes.[/yellow]")
        raise typer.Exit(code=2)

    orchestrator = Orchestrator(db_path=db or default_db_path())
    result = orchestrator.apply(plan_path=plan, checkpoint_path=checkpoint)
    console.log(f"Apply result: {result.summary}")


@app.command()
def undo(
    checkpoint: Path = typer.Option(..., "--checkpoint", exists=True, resolve_path=True),
    db: Optional[Path] = typer.Option(None, "--db", help="Path to event store DB"),
):
    """Undo a checkpointed apply operation.
    """
    orchestrator = Orchestrator(db_path=db or default_db_path())
    result = orchestrator.undo(checkpoint_path=checkpoint)
    console.log(f"Undo result: {result.summary}")


@app.command("dev-clean")
def dev_clean(
    path: Path = typer.Argument(..., exists=True, resolve_path=True),
    preset: str = typer.Option(
        "all", "--preset", help="Preset to target caches", case_sensitive=False
    ),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="List or delete via recycle bin"),
    db: Optional[Path] = typer.Option(None, "--db", help="Path to event store DB"),
):
    """List and optionally remove common dev caches under PATH.
    """
    orchestrator = Orchestrator(db_path=db or default_db_path())
    report = orchestrator.dev_clean(path=path, preset=preset, dry_run=dry_run)

    table = Table(title="Dev Clean Report")
    table.add_column("Path")
    table.add_column("Size (MB)", justify="right")
    table.add_column("Action")
    total_mb = 0.0
    for item in report.items:
        total_mb += item.size_mb
        table.add_row(str(item.path), f"{item.size_mb:.2f}", item.action)
    table.caption = f"Total: {total_mb:.2f} MB"
    console.print(table)


def main() -> None:
    """Entry point for `python -m cli.main`."""
    app()


if __name__ == "__main__":
    sys.exit(main())
