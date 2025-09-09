from __future__ import annotations

from pathlib import Path

from projections.file_index import FileIndex
from storage.event_store import EventRecord


def _rule_matched_event(path: Path) -> EventRecord:
    return EventRecord(
        id=0,
        ts=0,
        type="RuleMatched",
        data={"path": str(path), "rule_id": "R1"},
    )


def test_rulematched_adds_entry_with_zero_sizes(tmp_path: Path) -> None:
    idx = FileIndex()
    p = tmp_path / "some" / "file.txt"
    evt = _rule_matched_event(p)
    idx.apply(evt)

    meta = idx.entries.get(p)
    assert meta is not None
    assert meta.size == 0
    assert meta.mtime == 0.0

    # largest_folders should always return a list of tuples
    top = idx.largest_folders(limit=5)
    assert isinstance(top, list)
    for item in top:
        assert isinstance(item, tuple)
        assert isinstance(item[0], Path)
        assert isinstance(item[1], int)
