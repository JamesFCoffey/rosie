"""Deterministic rule engine (stub)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

from schemas.rules import RuleSet


def match_rules(paths: Iterable[Path], rules: RuleSet) -> Dict[Path, str]:
    """Return a mapping of path -> rule_id (very naive glob match)."""
    result: Dict[Path, str] = {}
    for p in paths:
        for rule in rules.rules:
            if any(p.match(glob) for glob in rule.include) and not any(
                p.match(glob) for glob in rule.exclude
            ):
                result[p] = rule.id
                break
    return result

