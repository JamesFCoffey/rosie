"""Embeddings loader and cache integration.

Provides a provider interface and a pure-Python fallback that computes
deterministic embeddings without network access. Exposes helpers to prepare
file texts (filename tokens + first KB preview), compute embeddings with
cache-by-content-hash semantics, and emit ``EmbeddingsComputed`` events.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

try:
    from blake3 import blake3 as _blake3

    def _hash_bytes(data: bytes) -> bytes:
        return _blake3(data).digest()

except Exception:  # pragma: no cover - fallback when blake3 unavailable
    import hashlib

    def _hash_bytes(data: bytes) -> bytes:
        return hashlib.sha256(data).digest()


from projections.embed_cache import EmbeddingCache
from schemas import events as ev
from storage.event_store import EventStore


class EmbedProvider(Protocol):
    """Protocol for embedding providers.

    Implementations must be pure functions of the provided texts with no
    external side effects and must not perform network access.
    """

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input text."""


class FallbackProvider:
    """Pure-Python deterministic embedding provider.

    Uses a simple hash-to-float scheme to generate fixed-size vectors. This is
    not semantically meaningful, but provides stable vectors for testing and
    offline usage.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = int(dim)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:  # noqa: D401
        return [_hash_text_to_floats(t, self.dim) for t in texts]


def _hash_text_to_floats(text: str, dim: int) -> list[float]:
    """Map ``text`` deterministically to ``dim`` floats in [0, 1]."""
    out: list[float] = []
    # Normalize whitespace for stability
    t = " ".join(text.split())
    for i in range(dim):
        h = _hash_bytes((t + f"|{i}").encode("utf-8"))
        # Use first 8 bytes as an unsigned integer
        val = int.from_bytes(h[:8], byteorder="big", signed=False)
        out.append(val / 2**64)
    return out


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")


def _split_tokens(name: str) -> list[str]:
    """Split a filename into lowercased tokens (underscores/dashes/camelCase)."""
    base = _NON_ALNUM_RE.sub(" ", name)
    parts: list[str] = []
    for frag in base.split():
        parts.extend(_CAMEL_RE.sub(" ", frag).split())
    return [p.lower() for p in parts if p]


def prepare_text_for_file(path: Path, *, max_preview_bytes: int = 1024) -> str:
    """Build embedding text from filename tokens + first KB preview.

    Args:
        path: File path to read.
        max_preview_bytes: Maximum number of bytes to read from the start.

    Returns:
        Combined lowercase text suitable for embedding providers.
    """
    name = path.name
    tokens = _split_tokens(name)
    ext = path.suffix.lower()
    preview = _read_preview_text(path, max_bytes=max_preview_bytes)
    # Keep structure simple and deterministic
    parts = [
        f"name:{name.lower()}",
        f"ext:{ext}",
        f"tokens:{' '.join(tokens)}",
        f"preview:{preview}",
    ]
    return "\n".join(parts)


def _read_preview_text(path: Path, *, max_bytes: int) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(max(0, int(max_bytes)))
    except Exception:
        return ""
    # Best-effort UTF-8 decode; strip NULs and normalize whitespace
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    text = text.replace("\x00", " ")
    return " ".join(text.split())


def _file_content_hash(path: Path, *, chunk_size: int = 64 * 1024) -> str:
    """Compute a stable hex digest of file content."""
    # Use streaming hashing; avoid loading large files entirely
    # Accumulate blake3 (or sha256) digest result at the end
    hasher_state: list[bytes] = []
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher_state.append(_hash_bytes(chunk))
    except Exception:
        return ""
    # Combine chunk digests deterministically and hash once more
    combined = b"".join(hasher_state) if hasher_state else b""
    return _hash_bytes(combined).hex()


def embed_files(
    *,
    paths: Sequence[Path],
    cache: EmbeddingCache,
    store: EventStore,
    provider: EmbedProvider | None = None,
    max_preview_bytes: int = 1024,
) -> int:
    """Compute and cache embeddings for provided files; emit event.

    Uses the embedding ``cache`` keyed by content hash. Skips directories and
    unreadable files. Emits a single ``EmbeddingsComputed`` event with the
    number of newly computed vectors.

    Args:
        paths: File paths to embed.
        cache: Embedding cache projection to store vectors.
        store: Event store to append ``EmbeddingsComputed``.
        provider: Optional embedding provider; defaults to ``FallbackProvider``.
        max_preview_bytes: Maximum bytes from each file for the text preview.

    Returns:
        Number of newly computed embeddings.
    """
    prov = provider or FallbackProvider()

    to_compute: list[tuple[str, Path]] = []  # (content_hash, path)
    texts: list[str] = []

    for p in paths:
        try:
            if not Path(p).is_file():
                continue
        except Exception:
            continue
        key = _file_content_hash(p)
        if not key:
            continue
        if cache.get(content_hash=key, mtime=0.0) is not None:
            continue
        to_compute.append((key, p))
        texts.append(prepare_text_for_file(p, max_preview_bytes=max_preview_bytes))

    new_count = 0
    if texts:
        vectors = prov.embed(texts)
        # Minimal validation: lengths must match
        if len(vectors) != len(texts):
            raise ValueError("Provider returned mismatched number of vectors")
        for (key, _p), vec in zip(to_compute, vectors):
            cache.put(content_hash=key, mtime=0.0, vector=vec)
            new_count += 1

    # Emit an informational event with the number computed (including 0)
    try:
        store.append(ev.EmbeddingsComputed(count=new_count))
    except Exception:
        # Keep computation side-effect free even if event append fails
        pass

    return new_count
