"""Rich TUI (scriptable) for reviewing a plan.

Provides a lightweight, non-interactive-friendly interface that can:
- Render a simple table (when a Console is provided), and
- Process a list of scripted commands for unit testing without a live terminal.

The TUI focuses on mapping user intents to domain events:
- Approvals map to ``UserApproved`` (emitted by the reviewer agent)
- All other edits map to ``CorrectionAdded`` with a descriptive note

Interactive key bindings can be added later; for tests we accept commands:
- "approve <item_id>"
- "reject <item_id> [reason...]"
- "relabel <item_id> <new_label...>"
- "split <item_id> <details...>"
- "merge <item_id1,item_id2,...> <details...>"
- "exclude <glob_or_path>"
- "rule <inline_rule_json_or_text>"
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

from projections.plan_view import PlanItem


@dataclass
class ReviewResult:
    approved_item_ids: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)


def _risk_score(action: str) -> int:
    a = action.lower()
    if a.startswith("delete"):
        return 3
    if a.startswith("move"):
        return 3
    if a.startswith("create"):
        return 1
    if a.startswith("rule:"):
        return 1
    return 2


def _sort_items(items: Sequence[PlanItem]) -> list[PlanItem]:
    # Higher risk first, lower confidence first (more likely to need review),
    # then by target path to keep deterministic order.
    return sorted(
        items,
        key=lambda it: (-_risk_score(it.action), it.confidence, str(it.target).lower()),
    )


def _render_table(items: Sequence[PlanItem], *, console: Console) -> None:
    table = Table(title="Review Plan (dry-run)")
    table.add_column("Action ID")
    table.add_column("Action")
    table.add_column("Target")
    table.add_column("Reason")
    table.add_column("Confidence")
    for it in items:
        table.add_row(it.id, it.action, str(it.target), it.reason, f"{it.confidence:.2f}")
    console.print(table)


def _parse_command(cmd: str) -> tuple[str, list[str]]:
    parts = cmd.strip().split()
    if not parts:
        return "", []
    return parts[0].lower(), parts[1:]


def run_review(
    items: Sequence[PlanItem],
    *,
    commands: Iterable[str] | None = None,
    console: Console | None = None,
) -> ReviewResult:
    """Run a review session in scripted or display-only mode.

    Args:
        items: Plan items to display/review.
        commands: Optional list/iterable of commands (non-interactive).
        console: Optional Rich console for display.

    Returns:
        ReviewResult summarizing approvals and textual corrections.
    """
    ordered = _sort_items(items)
    if console is not None:
        _render_table(ordered, console=console)

    result = ReviewResult()
    if not commands:
        # No interaction requested; return empty decisions
        return result

    # Build index for validation but do not block unknown ids (corrections can mention IDs)
    known_ids = {it.id for it in ordered}

    for raw in commands:
        op, args = _parse_command(raw)
        if not op:
            continue

        if op == "approve":
            # approve <id1>[,<id2>,...]
            if not args:
                continue
            id_arg = args[0]
            ids = [i.strip() for i in id_arg.split(",") if i.strip()]
            for iid in ids:
                # Accept approvals for any id; tests can pass synthetic ids
                if iid not in result.approved_item_ids:
                    result.approved_item_ids.append(iid)
            continue

        # The remaining commands map to textual corrections
        if op == "reject":
            # reject <id> [reason...]
            if not args:
                continue
            iid, note = args[0], " ".join(args[1:]).strip()
            if iid in known_ids:
                result.corrections.append(f"reject:{iid}:{note}" if note else f"reject:{iid}")
            else:
                result.corrections.append(f"reject:{iid}:{note}" if note else f"reject:{iid}")
            continue

        if op == "relabel":
            # relabel <id> <new_label...>
            if len(args) >= 2:
                iid, new_label = args[0], " ".join(args[1:]).strip()
                result.corrections.append(f"relabel:{iid}:{new_label}")
            continue

        if op == "split":
            # split <id> <details...>
            if len(args) >= 2:
                iid, detail = args[0], " ".join(args[1:]).strip()
                result.corrections.append(f"split:{iid}:{detail}")
            continue

        if op == "merge":
            # merge <id1,id2,...> <details...>
            if len(args) >= 2:
                id_list = args[0]
                detail = " ".join(args[1:]).strip()
                result.corrections.append(f"merge:{id_list}:{detail}")
            continue

        if op == "exclude":
            # exclude <glob_or_path>
            if args:
                result.corrections.append(f"exclude:{' '.join(args)}")
            continue

        if op == "rule":
            # rule <inline_rule_json_or_text>
            if args:
                result.corrections.append(f"rule:{' '.join(args)}")
            continue

        # Unknown operation: record as a freeform correction to preserve intent
        result.corrections.append(f"note:{raw}")

    return result

