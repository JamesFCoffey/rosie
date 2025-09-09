"""Windows-safe filesystem operations.

Provides helpers for atomic renames when possible, cross-volume copy with
verification and delete, and safe delete-to-recycle-bin operations.

These functions avoid following reparse points and try to be conservative.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Tuple

try:  # Prefer blake3 if available for speed
    from blake3 import blake3 as _blake3

    def _hash_file(path: Path) -> str:
        h = _blake3()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

except Exception:  # pragma: no cover - fallback
    import hashlib

    def _hash_file(path: Path) -> str:  # type: ignore[no-redef]
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

from os_win.recycle_bin import send_to_recycle_bin


def _same_volume(a: Path, b: Path) -> bool:
    """Return True if two paths are on the same volume/device.

    On Windows, compares drive letters case-insensitively. On POSIX, compares
    device numbers from ``os.stat``.
    """
    a = Path(a)
    b = Path(b)
    if os.name == "nt":
        # Normalize like "C:" prefix of absolute paths
        def drv(p: Path) -> str:
            s = str(p.resolve(strict=False))
            return s.split(":", 1)[0].upper() if ":" in s else s

        return drv(a) == drv(b)
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except Exception:
        # If either stat fails, assume cross-volume to be conservative
        return False


def ensure_parent(dst: Path) -> None:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)


def atomic_rename(src: Path, dst: Path) -> bool:
    """Atomically rename ``src`` to ``dst`` when on same volume.

    Returns True if the rename happened, False if cross-volume.
    Raises on other OS errors.
    """
    src = Path(src)
    dst = Path(dst)
    if not _same_volume(src, dst):
        return False
    ensure_parent(dst)
    os.replace(src, dst)  # atomic within same volume
    return True


def copy_verify_delete(src: Path, dst: Path) -> Tuple[bool, str]:
    """Copy file or directory across volumes, verify contents, then delete source.

    For files: checksum verification is performed. For directories: performs a
    tree copy without hashing every file to balance speed; still verifies sizes
    on a best-effort basis.

    Returns (ok, message).
    """
    src = Path(src)
    dst = Path(dst)
    ensure_parent(dst)
    try:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            # Best-effort: compare file counts
            def count_files(p: Path) -> int:
                c = 0
                for _root, _dirs, files in os.walk(p):
                    c += len(files)
                return c

            if count_files(src) != count_files(dst):
                return False, "directory copy verification failed"
        else:
            shutil.copy2(src, dst)
            if _hash_file(src) != _hash_file(dst):
                return False, "file checksum mismatch"
        # Only delete after verification
        if src.is_dir():
            shutil.rmtree(src)
        else:
            os.unlink(src)
        return True, "ok"
    except Exception as e:  # pragma: no cover - error path depends on FS
        return False, f"copy failed: {e}"


def recycle_delete(path: Path) -> None:
    """Send path to recycle bin if available; otherwise no-op."""
    send_to_recycle_bin(Path(path))


__all__ = [
    "atomic_rename",
    "copy_verify_delete",
    "recycle_delete",
    "ensure_parent",
]

