"""Conflict resolver.

Resolves target collisions, annotates risky operations, and adjusts
confidence for review. Pure function operating on in-memory plan items.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from os_win.onedrive import is_onedrive_path
from schemas.plan import PlanItemModel

T = TypeVar("T")


class Probe(Protocol):
    """Environment probe for safety checks.

    Implementations should perform lightweight checks without mutating state.
    """

    def is_locked(self, path: Path) -> bool:  # pragma: no cover - Protocol only
        ...

    def is_cross_volume(self, src: Path, dst: Path) -> bool:  # pragma: no cover
        ...


@dataclass
class _DefaultProbe:
    """Default best-effort probe.

    - ``is_locked``: returns False (caller can override in tests/Windows).
    - ``is_cross_volume``: simple drive/device heuristic.
    """

    def is_locked(self, path: Path) -> bool:  # pragma: no cover - trivial default
        return False

    def is_cross_volume(self, src: Path, dst: Path) -> bool:
        # Windows: different drives imply cross-volume
        try:
            if src.drive and dst.drive and (src.drive.lower() != dst.drive.lower()):
                return True
        except Exception:
            pass
        # POSIX and fallback: compare st_dev when available
        try:
            s_dev = src.stat().st_dev
            d_dev = dst.stat().st_dev
            return s_dev != d_dev
        except Exception:
            # If we cannot stat, be conservative and assume same volume
            return False


def _infer_move_src(reason: str) -> Path | None:
    """Infer source path from reason hints.

    Supports patterns like ``src=C:\\full\\path`` or suffix ``from C:\\path``.
    Returns None when not found or ambiguous.
    """
    r = reason.strip()
    if "src=" in r:
        try:
            return Path(r.split("src=", 1)[1].strip())
        except Exception:
            return None
    if " from " in r:
        tail = r.split(" from ", 1)[1].strip()
        if (len(tail) > 2) and (":" in tail or tail.startswith("/")):
            try:
                return Path(tail)
            except Exception:
                return None
    return None


def _suffix_path(p: Path, n: int) -> Path:
    """Return ``p`` suffixed with ``_n`` (or before extension for files).

    If ``n`` <= 1, returns ``p`` unchanged. For directories, suffix the
    last path component. For files, insert before the final extension.
    """
    if n <= 1:
        return p
    parent = p.parent
    name = p.name
    # Handle files with extensions vs directories
    if "." in name and not name.startswith("."):
        stem = name[: name.rfind(".")]
        ext = name[name.rfind(".") :]
        new_name = f"{stem}_{n}{ext}"
    else:
        new_name = f"{name}_{n}"
    return parent / new_name


def resolve(
    items: Iterable[PlanItemModel], *, root: Path, probe: Probe | None = None
) -> list[PlanItemModel]:
    """Resolve conflicts and annotate risks on plan items.

    Args:
        items: Input plan items (immutable input; output may carry modified fields).
        root: Scan root for context (unused by default but kept for future rules).
        probe: Optional environment probe. Defaults to ``_DefaultProbe``.

    Returns:
        New list of plan items with deduplicated targets and annotated reasons.
    """
    _ = root  # reserved for future use
    p = probe or _DefaultProbe()

    in_items = list(items)

    # Stable deterministic order: by normalized target, then action, then id
    def _norm_key(it: PlanItemModel) -> tuple[str, str, str]:
        try:
            tgt = str(it.target)
        except Exception:
            tgt = str(it.target)
        return (tgt.lower(), str(it.action), str(it.id))

    ordered = sorted(in_items, key=_norm_key)

    used: dict[str, int] = {}
    out: list[PlanItemModel] = []

    for it in ordered:
        action = it.action
        dst = Path(it.target)
        reason = it.reason
        conf = float(it.confidence)

        # 1) Deduplicate target collisions for create_dir and move
        if action in {"create_dir", "move"}:
            base_key = str(dst).lower()
            if base_key not in used:
                used[base_key] = 1
            else:
                # Find the first available suffix
                n = used[base_key] + 1
                cand = _suffix_path(dst, n)
                while str(cand).lower() in used:
                    n += 1
                    cand = _suffix_path(dst, n)
                dst = cand
                used[base_key] = n
                used[str(dst).lower()] = 1
        # Record reservation for unique targets even if not collided
        used.setdefault(str(dst).lower(), 1)

        # 2) Risk annotations
        prefixes: list[str] = []
        suffixes: list[str] = []

        if action == "move":
            src = _infer_move_src(reason)
            if src is not None:
                # Locked source
                try:
                    if p.is_locked(Path(src)):
                        prefixes.append("blocked: locked")
                        conf = min(conf, 0.4)
                except Exception:
                    pass
                # Cross-volume
                try:
                    if p.is_cross_volume(Path(src), Path(dst)):
                        suffixes.append("cross-volume")
                except Exception:
                    pass
                # OneDrive caution
                try:
                    if is_onedrive_path(Path(src)) or is_onedrive_path(Path(dst)):
                        prefixes.append("caution: onedrive")
                        conf = min(conf, 0.6)
                except Exception:
                    pass
        elif action == "create_dir":
            # Locked destination directory path
            try:
                if p.is_locked(Path(dst)):
                    prefixes.append("blocked: locked")
                    conf = min(conf, 0.4)
            except Exception:
                pass
            # OneDrive caution for directory creation under OneDrive
            try:
                if is_onedrive_path(Path(dst)):
                    prefixes.append("caution: onedrive")
                    conf = min(conf, 0.6)
            except Exception:
                pass

        # Rebuild reason string
        new_reason = reason
        if prefixes:
            new_reason = "; ".join(prefixes) + "; " + new_reason
        if suffixes:
            new_reason = new_reason + " [" + ", ".join(suffixes) + "]"

        out.append(
            PlanItemModel(
                id=it.id,  # caller may recompute ids post-resolution
                action=action,
                target=dst,
                reason=new_reason,
                confidence=max(0.0, min(1.0, conf)),
            )
        )

    return out
