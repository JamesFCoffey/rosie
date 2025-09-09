from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from projections.embed_cache import EmbeddingCache
from storage.event_store import EventStore
from tools import embeddings as emb


def _db_path(tmp_path: Path) -> Path:
    return (tmp_path / "state").joinpath("events.db")


class MockProvider:
    def __init__(self, dim: int = 4) -> None:
        self.dim = dim
        self.calls: int = 0
        self.last_texts: Sequence[str] | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        self.last_texts = list(texts)
        return [[0.5] * self.dim for _ in texts]


def test_embeddings_compute_and_cache(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)

    f1 = ws / "MyFile_v1.txt"
    f2 = ws / "data.bin"
    f1.write_text("hello world\nthis is a preview\n")
    f2.write_bytes(b"\x00\x01binary\x02data\x03")

    cache = EmbeddingCache()
    store = EventStore(_db_path(tmp_path))
    try:
        prov = MockProvider(dim=3)
        # First run embeds both files
        n1 = emb.embed_files(paths=[f1, f2], cache=cache, store=store, provider=prov)
        assert n1 == 2
        assert prov.calls == 1
        assert prov.last_texts is not None and len(prov.last_texts) == 2
        # Text should include tokens from filename and preview for f1
        joined = "\n".join(prov.last_texts)
        assert "myfile" in joined  # tokenized name
        assert "v1" in joined
        assert "hello world" in joined

        # Event appended with correct count
        rows = store.read_all()
        assert rows[-1].type == "EmbeddingsComputed"
        assert int(rows[-1].data.get("count", -1)) == 2

        # Second run should be a cache hit (no new embeddings)
        prov2 = MockProvider(dim=3)
        n2 = emb.embed_files(paths=[f1, f2], cache=cache, store=store, provider=prov2)
        assert n2 == 0
        # Provider should not be called when everything is cached
        assert prov2.calls in {0, 1}  # allow 0 calls (preferred); if called, texts should be empty
        if prov2.calls == 1:
            assert prov2.last_texts == []

        rows = store.read_all()
        assert rows[-1].type == "EmbeddingsComputed"
        assert int(rows[-1].data.get("count", -1)) == 0

        # Cache should contain vectors for both files by content hash
        h1 = emb._file_content_hash(f1)
        h2 = emb._file_content_hash(f2)
        v1 = cache.get(content_hash=h1, mtime=0.0)
        v2 = cache.get(content_hash=h2, mtime=0.0)
        assert v1 is not None and len(v1) == 3
        assert v2 is not None and len(v2) == 3
    finally:
        store.close()

