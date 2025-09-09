from __future__ import annotations

from pathlib import Path

import tools.clustering as cl


def test_fallback_when_hdbscan_all_noise(monkeypatch, tmp_path: Path) -> None:
    # Force the HDBSCAN path to produce all-noise labels
    def _fake_hdbscan(vectors, *, min_cluster_size: int = 3):  # type: ignore[override]
        n = len(vectors)
        return ([-1] * n, [0.1] * n)

    monkeypatch.setattr(cl, "_try_hdbscan", _fake_hdbscan)

    # Two near-identical vectors and one far; fallback should group the pair
    a, b, c = Path("a.txt"), Path("b.txt"), Path("c.bin")
    v: list[list[float]] = [
        [1.0, 0.0, 0.0],
        [0.98, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]

    items = cl.cluster_vectors(paths=[a, b, c], vectors=v, store=None)
    cids = [it.cluster_id for it in items]
    # Ensure fallback produced at least one non-noise assignment
    assert any(cid != -1 for cid in cids)

