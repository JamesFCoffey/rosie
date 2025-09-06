"""Checkpoint writer (stub)."""

from __future__ import annotations

from pathlib import Path

from schemas.checkpoint import Checkpoint


def write_checkpoint(checkpoint: Checkpoint) -> Path:
    # Stub: do nothing and return path
    return checkpoint.path

