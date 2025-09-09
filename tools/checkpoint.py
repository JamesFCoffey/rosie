"""Checkpoint journal utilities.

Provides a simple, append-friendly JSON checkpoint format used by the executor
to support reliable undo. The journal is designed to be safe:

- Writes are atomic via temp files + replace
- Paths are serialized as strings for portability
- The format is deterministic and validated via Pydantic models
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from schemas.checkpoint import Checkpoint, CheckpointAction


def _atomic_write_text(path: Path, data: str) -> None:
    """Write text to ``path`` atomically.

    Uses a sibling ``.tmp`` file and ``os.replace`` to ensure the file either
    exists entirely or not at all.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(data)
    # os.replace is atomic on both Windows and POSIX
    import os

    os.replace(tmp, path)


def new_checkpoint_path(plan_id: str, base_dir: Path | None = None) -> Path:
    """Compute a default checkpoint path for a plan id.

    Args:
      plan_id: Deterministic plan identifier.
      base_dir: Optional base directory (defaults to ``~/.rosie/checkpoints``).

    Returns:
      A path like ``~/.rosie/checkpoints/<ts>-<pid>.json``.
    """
    ts = int(time.time())
    if base_dir is None:
        base_dir = Path.home() / ".rosie" / "checkpoints"
    base_dir.mkdir(parents=True, exist_ok=True)
    # Keep plan id short in file name while remaining unique enough for tests
    pid_short = plan_id[:12]
    return base_dir / f"{ts}-{pid_short}.json"


def write_checkpoint(checkpoint: Checkpoint) -> Path:
    """Persist a checkpoint atomically.

    Args:
      checkpoint: Checkpoint model including ``path`` and ``actions``.

    Returns:
      The path written.
    """
    payload = checkpoint.model_dump(mode="json")
    text = json.dumps(payload, indent=2, sort_keys=True)
    _atomic_write_text(checkpoint.path, text)
    return checkpoint.path


def read_checkpoint(path: Path) -> Checkpoint:
    """Load a checkpoint from disk."""
    data = Path(path).read_text()
    return Checkpoint.from_json(data)


def append_action(path: Path, action: CheckpointAction) -> None:
    """Append an action to a checkpoint journal by rewriting the file.

    The file is re-written atomically to avoid partial updates. Given the
    relatively small number of actions in typical plans, this keeps the code
    simple while remaining robust.
    """
    p = Path(path)
    if p.exists():
        ck = read_checkpoint(p)
        actions: list[CheckpointAction] = list(ck.actions)
    else:
        ck = Checkpoint(path=p, actions=[])
        actions = []
    actions.append(action)
    ck = Checkpoint(path=p, actions=actions)
    write_checkpoint(ck)


__all__ = [
    "new_checkpoint_path",
    "write_checkpoint",
    "read_checkpoint",
    "append_action",
]
