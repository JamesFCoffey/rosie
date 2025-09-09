"""Recycle bin operations (safe, stubbed when unavailable).

Implements a best-effort, in-process send-to-Recycle-Bin on Windows using
``ctypes`` bindings to ``SHFileOperationW``. On non-Windows platforms or when
the API is unavailable, the function becomes a no-op so callers can safely
depend on it without risking accidental deletion.

This module performs no network access and avoids any global side effects.
"""

from __future__ import annotations

from pathlib import Path


def _is_windows() -> bool:
    import os

    return os.name == "nt"


def send_to_recycle_bin(p: Path) -> None:
    """Move ``p`` to the Recycle Bin if supported; otherwise no-op.

    This is intentionally conservative: when the Windows shell operation is not
    available, the function refuses to delete and simply returns. Callers that
    require strict guarantees should check platform capabilities separately.

    Args:
      p: File or directory path to recycle.
    """
    if not _is_windows():
        # Stubbed behavior outside Windows: do nothing.
        return None

    try:
        import ctypes
        from ctypes import wintypes

        # Constants from shellapi.h
        FO_DELETE = 3
        FOF_SILENT = 0x0004
        FOF_NOCONFIRMATION = 0x0010
        FOF_ALLOWUNDO = 0x0040

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),  # double-null-terminated
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.USHORT),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        SHFileOperationW = ctypes.windll.shell32.SHFileOperationW  # type: ignore[attr-defined]

        # Build double-null-terminated source list
        src = str(Path(p)) + "\x00\x00"
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = src
        op.pTo = None
        op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None

        res = SHFileOperationW(ctypes.byref(op))
        # Non-zero indicates failure; we intentionally do not delete as a
        # fallback to preserve safety.
        if res != 0:
            # Leave as no-op on failure to keep dry-run semantics safe.
            return None
    except Exception:
        # If the shell API is not available or something goes wrong, do not
        # delete. The caller can decide to unlink with explicit confirmation.
        return None


__all__ = ["send_to_recycle_bin"]
