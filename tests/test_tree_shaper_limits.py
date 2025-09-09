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
