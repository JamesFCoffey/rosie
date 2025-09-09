"""Deterministic rule engine and YAML loader.

Implements a privacy-safe, deterministic rule matcher with precedence:

path > glob > ext > semantic

The engine supports size/age conditions and allow/deny lists in addition to
legacy ``include``/``exclude`` fields. It can also emit ``RuleMatched`` events
to the event store for downstream projections.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from schemas import events as ev
from schemas.rules import RuleSet
from storage.event_store import EventStore

# ----------------------------
# Matching helpers and scoring
# ----------------------------


def _norm_ext(ext: str) -> str:
    e = ext.lower().strip()
    if not e:
        return ""
    if e.startswith("."):
        return e
    return "." + e


def _matches_any(p: Path, patterns: Sequence[str]) -> bool:
    name = p.name
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        if p.match(pat) or name == pat:
            return True
    return False


def _file_stat(p: Path) -> os.stat_result | None:
    try:
        return os.stat(p)
    except Exception:
        return None


def _size_age_ok(
    p: Path,
    *,
    min_size: int | None,
    max_size: int | None,
    min_age_days: float | None,
    max_age_days: float | None,
) -> bool:
    st = _file_stat(p)
    if st is None:
        return False
    size = int(getattr(st, "st_size", 0))
    mtime = float(getattr(st, "st_mtime", 0.0))
    now = time.time()
    age_days = max(0.0, (now - mtime) / 86400.0)

    if min_size is not None and size < min_size:
        return False
    if max_size is not None and size > max_size:
        return False
    if min_age_days is not None and age_days < min_age_days:
        return False
    if max_age_days is not None and age_days > max_age_days:
        return False
    return True


def _rule_match_score(p: Path, rule_json: dict) -> tuple[int, bool]:
    """Return (score, matched) for a rule against path.

    Score encodes precedence: path=3, glob=2, ext=1, none=0. ``matched`` is the
    final decision including allow/deny and size/age constraints.
    """
    # Support both new fields and legacy include/exclude
    paths: list[str] = list(rule_json.get("paths") or [])
    globs: list[str] = list(rule_json.get("globs") or [])
    exts: list[str] = [_norm_ext(e) for e in (rule_json.get("exts") or [])]
    include: list[str] = list(rule_json.get("include") or [])
    exclude: list[str] = list(rule_json.get("exclude") or [])
    allow: list[str] = list(rule_json.get("allow") or [])
    deny: list[str] = list(rule_json.get("deny") or [])

    # Conditions
    min_size = rule_json.get("min_size")
    max_size = rule_json.get("max_size")
    min_age_days = rule_json.get("min_age_days")
    max_age_days = rule_json.get("max_age_days")

    # Determine category match
    score = 0
    matched = False

    # Path exact or prefix match (normalize to absolute/relative insensitive)
    # Compare string forms for determinism
    spath = str(p)
    if paths:
        for pat in paths:
            if not pat:
                continue
            # Exact match or relative match on name
            if spath == pat or p.name == pat:
                score = max(score, 3)
                matched = True
                break

    # Glob (legacy include + new globs)
    if not matched and (globs or include):
        if _matches_any(p, [*globs, *include]):
            score = max(score, 2)
            matched = True

    # Extension
    if not matched and exts:
        if (p.suffix.lower() or "") in exts:
            score = max(score, 1)
            matched = True

    # If no category matched, early return
    if not matched:
        return 0, False

    # Apply allow/deny and legacy exclude
    if deny and _matches_any(p, deny):
        return score, False
    if exclude and _matches_any(p, exclude):
        return score, False
    if allow and not _matches_any(p, allow):
        return score, False

    # Size/age constraints (files only). If it's a directory, skip size checks
    if p.is_file():
        if not _size_age_ok(
            p,
            min_size=min_size,
            max_size=max_size,
            min_age_days=min_age_days,
            max_age_days=max_age_days,
        ):
            return score, False

    return score, True


def match_rules(paths: Iterable[Path], rules: RuleSet) -> dict[Path, str]:
    """Return a deterministic mapping of ``path -> rule_id``.

    Applies precedence: path > glob > ext. Within the same precedence, retains
    the first matching rule order from the provided RuleSet.
    """
    result: dict[Path, str] = {}
    for p in paths:
        best_score = -1
        best_rule_id: str | None = None
        for rule in rules.rules:
            rj = rule.model_dump(mode="json")
            score, ok = _rule_match_score(p, rj)
            if not ok:
                continue
            if score > best_score:
                best_score = score
                best_rule_id = rule.id
                # Highest possible score is 3; break early
                if best_score == 3:
                    break
        if best_rule_id is not None:
            result[p] = best_rule_id
    return result


def emit_rule_matches(paths: Iterable[Path], rules: RuleSet, store: EventStore) -> int:
    """Evaluate rules over paths and emit ``RuleMatched`` events.

    Args:
        paths: Iterable of filesystem paths to evaluate.
        rules: RuleSet to apply.
        store: EventStore to append events to.

    Returns:
        Number of ``RuleMatched`` events emitted.
    """
    matches = match_rules(paths, rules)
    count = 0
    for p, rid in matches.items():
        try:
            store.append(ev.RuleMatched(path=p, rule_id=rid))
            count += 1
        except Exception:
            # Keep deterministic behavior even if one append fails
            continue
    return count


# -------------
# YAML loading
# -------------


def load_rules_from_yaml(path: Path) -> RuleSet:
    """Load rules from YAML or JSON with clear error handling.

    Behavior:
    - If the file extension is ``.json`` (or the content looks like JSON), parse as JSON.
    - If the file extension is ``.yaml``/``.yml`` and PyYAML is unavailable, raise a
      clear error instructing to install ``pyyaml`` or provide a JSON file instead.
    - Otherwise, parse as YAML using ``yaml.safe_load``.
    """
    text = Path(path).read_text(encoding="utf-8")
    data: dict
    ext = path.suffix.lower()

    def _parse_json() -> dict:
        import json

        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise TypeError("Rules JSON must be a mapping at top-level")
        return obj

    looks_json = text.lstrip().startswith("{") or text.lstrip().startswith("[")

    if ext == ".json" or (ext not in {".yaml", ".yml"} and looks_json):
        data = _parse_json()
    else:
        try:
            # Use dynamic import via builtins to respect patched import hooks in tests
            yaml = __import__("yaml")
            data = yaml.safe_load(text) or {}
            if not isinstance(data, dict):
                raise TypeError("Rules YAML must be a mapping at top-level")
        except ModuleNotFoundError as e:
            # If YAML is unavailable but content looks like JSON, fall back gracefully
            if looks_json:
                data = _parse_json()
            else:
                raise RuntimeError(
                    "PyYAML is not installed. Install 'pyyaml' or provide a .json rules file."
                ) from e
        except Exception:
            # As a last resort, if content actually looks like JSON, try it
            if looks_json:
                data = _parse_json()
            else:
                raise

    # Pydantic will validate and provide defaults
    return RuleSet.model_validate(data)
