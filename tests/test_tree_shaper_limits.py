from __future__ import annotations

from pathlib import Path

from tools.tree_shaper import sanitize_label, shape_cluster_moves


def test_shape_cluster_moves_max_children(tmp_path: Path) -> None:
    root = tmp_path
    label = "My:Cluster?Name"
    members = [root / f"f{i}.txt" for i in range(7)]
    for p in members:
        p.write_text("x")

    dirs, moves = shape_cluster_moves(
        root=root, label=label, members=members, max_depth=2, max_children=3
    )

    # Top-level directory plus 3 parts (ceil(7/3) == 3)
    s = sanitize_label(label)
    assert (root / s) in dirs
    assert (root / s / "part_001") in dirs
    assert (root / s / "part_002") in dirs
    assert (root / s / "part_003") in dirs

    # Moves should cover all members
    targets = {dst for (_src, dst) in moves}
    assert len(targets) == len(members)
    # All targets reside under the created subfolders
    assert all(str(t).startswith(str(root / s)) for t in targets)


def test_depth_and_width_pruning(tmp_path: Path) -> None:
    # With max_depth=2 and max_children=3, capacity = 3*3 = 9 under base
    root = tmp_path
    label = "Deep*Cluster"
    members = [root / f"file_{i}.dat" for i in range(25)]
    for p in members:
        p.write_text("x")

    dirs, moves = shape_cluster_moves(
        root=root, label=label, members=members, max_depth=2, max_children=3
    )

    # No destination path should exceed depth of 3 below root
    for _src, dst in moves:
        rel = dst.relative_to(root)
        assert len(rel.parts) <= 3

    # Per-directory child counts must be <= max_children
    from collections import defaultdict

    child_counts: dict[Path, set[Path]] = defaultdict(set)
    # Count directory children (subdirs) via dirs list
    for d in set(dirs):
        if d == root:
            continue
        parent = d.parent
        child_counts[parent].add(d)
    # Count file children via moves
    for _src, dst in moves:
        child_counts[dst.parent].add(dst)
    assert all(len(children) <= 3 for children in child_counts.values())

    # Capacity is bounded to 9 (3 subdirs x 3 files each) under base
    assert len(moves) <= 9


def test_sanitize_label_windows_reserved() -> None:
    assert sanitize_label("CON").upper() != "CON"
    assert sanitize_label("AUX").upper() != "AUX"
    assert sanitize_label("COM1").upper() != "COM1"
    # Illegal chars replaced
    s = sanitize_label("bad:name|here*")
    assert ":" not in s and "|" not in s and "*" not in s
