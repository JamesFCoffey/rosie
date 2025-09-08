"""Semantic clustering with HDBSCAN and fallbacks.

Provides a batchable API to cluster embedding vectors with a preference for
``hdbscan``. Falls back to scikit-learn AgglomerativeClustering, and finally
to a simple cosine-similarity threshold grouping when neither library is
available. Emits ``ClustersFormed`` events with per-item cluster ids and
confidences, and includes a basic TF‑IDF labeler over names/snippets.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from schemas import events as ev
from storage.event_store import EventStore
from tools.embeddings import _split_tokens


def cluster_by_extension(paths: Iterable[Path]) -> Dict[str, List[Path]]:
    groups: Dict[str, List[Path]] = {}
    for p in paths:
        ext = p.suffix.lower() or "<none>"
        groups.setdefault(ext, []).append(p)
    return groups


# -----------------------
# TF-IDF labeling helpers
# -----------------------

def _tokenize_texts(texts: Sequence[str]) -> List[List[str]]:
    return [[t for t in _split_tokens(txt)] for txt in texts]


def _tf_idf_labels(texts: Sequence[str], assignments: Sequence[int], *, top_k: int = 1) -> Dict[int, str]:
    """Compute simple TF‑IDF labels per cluster.

    Args:
        texts: One text per document.
        assignments: Cluster id per document (``-1`` for noise).
        top_k: Number of tokens to use for the label (space-joined).

    Returns:
        Mapping ``cluster_id -> label``. Noise (``-1``) is excluded.
    """
    tokens_per_doc = _tokenize_texts(texts)
    n_docs = max(1, len(tokens_per_doc))
    # Document frequency
    df: MutableMapping[str, int] = defaultdict(int)
    for toks in tokens_per_doc:
        for tok in set(toks):
            df[tok] += 1

    # Accumulate TF-IDF per cluster
    scores: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for toks, cid in zip(tokens_per_doc, assignments):
        if cid == -1:
            continue
        # Term freq for this document
        tf: Dict[str, int] = defaultdict(int)
        for t in toks:
            tf[t] += 1
        for t, f in tf.items():
            idf = math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0  # smooth
            scores[cid][t] += float(f) * idf

    labels: Dict[int, str] = {}
    for cid, per_tok in scores.items():
        if not per_tok:
            continue
        top = sorted(per_tok.items(), key=lambda kv: kv[1], reverse=True)[: max(1, top_k)]
        label = " ".join(t for (t, _s) in top)
        labels[cid] = label or f"cluster-{cid}"
    return labels


# -------------------
# Clustering backends
# -------------------

def _try_hdbscan(vectors: Sequence[Sequence[float]], *, min_cluster_size: int = 3):
    try:
        import hdbscan  # type: ignore

        clusterer = hdbscan.HDBSCAN(min_cluster_size=max(2, int(min_cluster_size)))
        labels = clusterer.fit_predict(vectors)
        # probabilities_ aligns with labels
        probs = getattr(clusterer, "probabilities_", None)
        if probs is None:
            probs = [1.0 if int(l) != -1 else 0.0 for l in labels]
        return list(map(int, labels)), [float(p) for p in probs]
    except Exception:
        return None


def _try_agglomerative(vectors: Sequence[Sequence[float]], *, n_clusters: int | None = None):
    try:
        from sklearn.cluster import AgglomerativeClustering  # type: ignore

        n = len(vectors)
        k = int(n_clusters) if n_clusters else max(2, min(5, n // 2 or 1))
        model = AgglomerativeClustering(n_clusters=k)
        labels = model.fit_predict(vectors)
        # No probabilities; assign neutral confidence
        probs = [0.5] * len(vectors)
        return list(map(int, labels)), probs
    except Exception:
        return None


def _cosine_sim(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _fallback_threshold(vectors: Sequence[Sequence[float]], *, sim_threshold: float = 0.92):
    n = len(vectors)
    labels = [-1] * n
    current_label = 0
    visited = [False] * n
    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        # Seed a new cluster with i and attach close neighbors
        labels[i] = current_label
        for j in range(i + 1, n):
            if visited[j]:
                continue
            if _cosine_sim(vectors[i], vectors[j]) >= sim_threshold:
                labels[j] = current_label
                visited[j] = True
        # If singleton, mark as noise
        if labels.count(current_label) <= 1:
            labels[i] = -1
        else:
            current_label += 1
    probs = [1.0 if l != -1 else 0.0 for l in labels]
    return labels, probs


# -----------------------------
# Public, batchable clustering
# -----------------------------

def cluster_vectors(
    *,
    paths: Sequence[Path],
    vectors: Sequence[Sequence[float]],
    store: EventStore | None = None,
    texts: Sequence[str] | None = None,
    min_cluster_size: int = 3,
) -> List[ev.ClusterAssignment]:
    """Cluster vectors and optionally emit a ``ClustersFormed`` event.

    Args:
        paths: Files corresponding to the vectors.
        vectors: Embedding vectors aligned with ``paths``.
        store: Optional event store to emit ``ClustersFormed``.
        texts: Optional texts (names/snippets) for labeling.
        min_cluster_size: Minimum cluster size for density-based clustering.

    Returns:
        A list of ``ClusterAssignment`` records (noise has ``cluster_id=-1``).
    """
    if len(paths) != len(vectors):
        raise ValueError("paths and vectors must have same length")

    # Prefer HDBSCAN, then Agglomerative, then threshold fallback.
    # If HDBSCAN degrades to all-noise labels, fall back to force grouping.
    result = _try_hdbscan(vectors, min_cluster_size=min_cluster_size)
    if result is not None:
        labels, probs = result
        if not any(l != -1 for l in labels):
            result = None  # force fallback if all noise
    if result is None:
        result = _try_agglomerative(vectors)
    if result is None:
        result = _fallback_threshold(vectors)
    labels, probs = result

    # Basic labeling
    lbl_map: Dict[int, str] = {}
    if texts is None:
        texts = [p.stem for p in paths]
    try:
        lbl_map = _tf_idf_labels(texts, labels, top_k=1)
    except Exception:
        lbl_map = {}

    items: List[ev.ClusterAssignment] = []
    for p, cid, pr in zip(paths, labels, probs):
        items.append(ev.ClusterAssignment(path=Path(p), cluster_id=int(cid), confidence=float(pr), label=lbl_map.get(int(cid))))

    if store is not None:
        try:
            # Count non-noise clusters
            cluster_ids = sorted({it.cluster_id for it in items if it.cluster_id != -1})
            store.append(ev.ClustersFormed(count=len(cluster_ids), items=items))
        except Exception:
            pass

    return items
