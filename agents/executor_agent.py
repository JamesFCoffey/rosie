"""ExecutorAgent.

Applies approved actions with checkpointing using Windows-safe operations.
Emits events for ApplyStarted/ActionApplied via the orchestrator's event store.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from os_win.onedrive import is_onedrive_path
from projections.base import replay
from projections.plan_view import PlanProjection, PlanView
from schemas import events as ev
from schemas.checkpoint import Checkpoint, CheckpointAction
from storage.event_store import EventStore
from tools import checkpoint as ck
from tools import file_ops

# Conservative defaults; tests can override via parameters to apply().
MAX_ACTIONS_DEFAULT = 1000
MAX_TOTAL_MOVE_BYTES_DEFAULT = 10 * 1024 * 1024 * 1024  # 10 GiB


@dataclass
class ExecutionResult:
    applied: int
    skipped: int
    summary: str


class ExecutorAgent:
    def __init__(self, store: EventStore) -> None:
        self.store = store

    def _infer_move_src(self, reason: str) -> Path | None:
        """Best-effort source path inference for move actions.

        Supports patterns like "... from C:\\full\\path" or "src=C:\\full\\path".
        Returns None when not found.
        """
        r = reason.strip()
        if "src=" in r:
            try:
                return Path(r.split("src=", 1)[1].strip())
            except Exception:
                return None
        if " from " in r:
            tail = r.split(" from ", 1)[1].strip()
            # If tail looks like a path, use it; otherwise, give up.
            if (len(tail) > 2) and (":" in tail or tail.startswith("/")):
                return Path(tail)
        return None

    def apply(
        self,
        plan: PlanView,
        *,
        checkpoint_path: Path | None,
        max_actions: int | None = None,
        max_total_move_bytes: int | None = None,
        force: bool = False,
    ) -> ExecutionResult:
        # Materialize deterministic plan id for ApplyStarted event
        proj = PlanProjection()
        replay(proj, self.store)
        current = proj.current_plan()
        self.store.append(ev.ApplyStarted(plan_id=current.id))

        # Safety: refuse if too many actions in one run
        lim_actions = max_actions if max_actions is not None else MAX_ACTIONS_DEFAULT
        if len(plan.items) > lim_actions:
            return ExecutionResult(
                applied=0,
                skipped=len(plan.items),
                summary=f"refused: too_many_actions>{lim_actions}",
            )

        # Safety: OneDrive guard (unless forced). If any move targets or sources
        # an OneDrive path, refuse by default to avoid sync/placeholder issues.
        for it in plan.items:
            try:
                if it.action == "move":
                    src = self._infer_move_src(it.reason)
                    dst = Path(it.target)
                    if (src and is_onedrive_path(src)) or is_onedrive_path(dst):
                        if not force:
                            return ExecutionResult(
                                applied=0,
                                skipped=len(plan.items),
                                summary="refused: onedrive_guard (use --force to override)",
                            )
            except Exception:
                # If detection fails, do not block; executor handles errors per item
                continue

        # Safety: total move size threshold
        lim_move = (
            max_total_move_bytes
            if max_total_move_bytes is not None
            else MAX_TOTAL_MOVE_BYTES_DEFAULT
        )
        if lim_move >= 0:
            total_bytes = 0
            for it in plan.items:
                if it.action != "move":
                    continue
                src = self._infer_move_src(it.reason)
                if src is None:
                    continue
                try:
                    p = Path(src)
                    if p.is_file():
                        total_bytes += int(p.stat().st_size)
                    elif p.is_dir():
                        # Best-effort: sum file sizes; may be approximate
                        import os as _os

                        for dp, _dn, files in _os.walk(p):
                            for fn in files:
                                try:
                                    total_bytes += int(Path(dp, fn).stat().st_size)
                                except Exception:
                                    continue
                except Exception:
                    continue
            if total_bytes > lim_move:
                return ExecutionResult(
                    applied=0,
                    skipped=len(plan.items),
                    summary=f"refused: move_size>{lim_move}",
                )

        # Resolve checkpoint path and initialize journal
        ck_path = checkpoint_path or ck.new_checkpoint_path(current.id)
        journal = Checkpoint(path=ck_path, actions=[])
        ck.write_checkpoint(journal)

        applied = 0
        skipped = 0

        for it in plan.items:
            status = "skipped"
            message = None
            try:
                if it.action == "create_dir":
                    file_ops.ensure_parent(it.target)
                    Path(it.target).mkdir(parents=True, exist_ok=True)
                    ck.append_action(
                        ck_path, CheckpointAction(item_id=it.id, op="mkdir", src=it.target)
                    )
                    status = "applied"
                    applied += 1
                elif it.action == "move":
                    # Infer source path; skip if unavailable
                    src = self._infer_move_src(it.reason)
                    if src is None or not Path(src).exists():
                        skipped += 1
                        status = "skipped"
                        message = "source not found"
                    else:
                        dst = Path(it.target)
                        if file_ops.atomic_rename(src, dst):
                            ck.append_action(
                                ck_path,
                                CheckpointAction(item_id=it.id, op="move", src=src, dst=dst),
                            )
                            applied += 1
                            status = "applied"
                        else:
                            ok, msg = file_ops.copy_verify_delete(src, dst)
                            if ok:
                                ck.append_action(
                                    ck_path,
                                    CheckpointAction(item_id=it.id, op="move_xv", src=src, dst=dst),
                                )
                                applied += 1
                                status = "applied"
                            else:
                                skipped += 1
                                status = "skipped"
                                message = msg
                else:
                    # Unknown action type: do not mutate
                    skipped += 1
                    status = "skipped"
                    message = f"unknown action: {it.action}"
            except Exception as e:  # pragma: no cover - defensive guard
                skipped += 1
                status = "error"
                message = str(e)
            finally:
                try:
                    self.store.append(
                        ev.ActionApplied(item_id=it.id, status=status, message=message)
                    )
                except Exception:
                    pass

        summary = f"applied={applied} skipped={skipped} checkpoint={ck_path}"
        return ExecutionResult(applied=applied, skipped=skipped, summary=summary)

    def undo(self, *, checkpoint_path: Path) -> ExecutionResult:
        """Undo actions recorded in the provided checkpoint.

        Undo is best-effort and idempotent: missing paths are ignored.
        """
        ckpt = ck.read_checkpoint(checkpoint_path)
        # Walk in reverse application order
        undone = 0
        skipped = 0
        for act in reversed(list(ckpt.actions)):
            try:
                if act.op == "mkdir":
                    # Remove created directory via recycle bin where possible
                    if Path(act.src).exists():
                        if __import__("os").name == "nt":
                            file_ops.recycle_delete(act.src)
                        else:
                            # On non-Windows, remove directly for tests
                            import shutil

                            shutil.rmtree(act.src, ignore_errors=True)
                        undone += 1
                    else:
                        skipped += 1
                elif act.op in {"move", "move_xv"}:
                    # Move back if possible
                    src = Path(act.dst) if act.dst is not None else None
                    dst = Path(act.src)
                    if src is None or not src.exists():
                        skipped += 1
                        continue
                    if file_ops.atomic_rename(src, dst):
                        undone += 1
                    else:
                        ok, _msg = file_ops.copy_verify_delete(src, dst)
                        if ok:
                            undone += 1
                        else:
                            skipped += 1
                else:
                    skipped += 1
            except Exception:  # pragma: no cover - defensive
                skipped += 1

        try:
            self.store.append(ev.UndoPerformed(checkpoint_path=checkpoint_path))
        except Exception:
            pass
        return ExecutionResult(
            applied=undone, skipped=skipped, summary=f"undone={undone} skipped={skipped}"
        )
