"""Embedding dedup helpers for factory intake (BL-20260702-01).

Nothing here touches a real embedding backend: ``install_fake_embedder``
swaps ``httpx.Client`` for a ``MockTransport`` one, so the suite stays offline
and deterministic while still exercising the cache, the provenance event, and
the fail-open path.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable

import httpx
import pytest

from law_ai.lsat.factory import embeddings
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.services import bank as bank_mod


def hash_vector(text: str, dims: int = 16) -> list[float]:
    """Deterministic pseudo-random unit-ish vector — distinct texts score low."""
    digest = hashlib.sha256(text.lower().encode("utf-8")).digest()
    return [(digest[i] - 128) / 128.0 for i in range(dims)]


def install_fake_embedder(
    monkeypatch: pytest.MonkeyPatch,
    vector_for: Callable[[str], list[float]] = hash_vector,
    *,
    calls: list[str] | None = None,
    fail: bool = False,
) -> None:
    """Route ``/api/embeddings`` at an in-process handler for this test."""
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            raise httpx.ConnectError("connection refused", request=request)
        prompt = json.loads(request.content.decode("utf-8"))["prompt"]
        if calls is not None:
            calls.append(prompt)
        return httpx.Response(200, json={"embedding": vector_for(prompt)})

    def factory(**kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "Client", factory)


class TestCosine:
    def test_identical_vectors_score_one(self) -> None:
        assert embeddings.cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self) -> None:
        assert embeddings.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_degenerate_inputs_score_zero(self) -> None:
        assert embeddings.cosine([], [1.0]) == 0.0
        assert embeddings.cosine([1.0, 2.0], [1.0]) == 0.0
        assert embeddings.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestBankRevision:
    def test_revision_tracks_bank_contents(self, factory_env: FactoryConfig) -> None:
        first = embeddings.bank_revision()
        assert first == embeddings.bank_revision()
        path = bank_mod.DATA_DIR / "lr_bank.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["items"] = payload["items"][:-1]
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert embeddings.bank_revision() != first


class TestEmbeddingIndex:
    def test_embeds_and_caches_per_bank_revision(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        install_fake_embedder(monkeypatch, calls=calls)

        index = embeddings.EmbeddingIndex.from_config(factory_env)
        vectors = index.embed(["alpha stem", "beta stem"])
        index.flush()

        assert len(vectors) == 2 and len(vectors[0]) == 16
        assert calls == ["alpha stem", "beta stem"]
        assert index.computed == 2
        assert embeddings.bank_revision() in index.cache_path.name
        assert index.cache_path.is_file()

        warm = embeddings.EmbeddingIndex.from_config(factory_env)
        warm.embed(["alpha stem", "beta stem"])
        assert calls == ["alpha stem", "beta stem"]  # served from the cache
        assert warm.computed == 0 and warm.cached_hits == 2

    def test_repeated_text_in_one_batch_is_embedded_once(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        install_fake_embedder(monkeypatch, calls=calls)
        index = embeddings.EmbeddingIndex.from_config(factory_env)
        index.embed(["same stem", "same stem", "other"])
        assert calls == ["same stem", "other"]

    def test_new_bank_revision_inherits_cached_vectors(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        install_fake_embedder(monkeypatch, calls=calls)
        first = embeddings.EmbeddingIndex.from_config(factory_env)
        first.embed(["alpha stem"])
        first.flush()

        path = bank_mod.DATA_DIR / "lr_bank.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["items"] = payload["items"][:-1]
        path.write_text(json.dumps(payload), encoding="utf-8")

        second = embeddings.EmbeddingIndex.from_config(factory_env)
        assert second.cache_path != first.cache_path
        second.embed(["alpha stem"])
        second.flush()
        assert calls == ["alpha stem"]  # no re-embedding across the revision
        assert second.cache_path.is_file()

    def test_backend_failure_raises_embedding_unavailable(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_embedder(monkeypatch, fail=True)
        index = embeddings.EmbeddingIndex.from_config(factory_env)
        with pytest.raises(embeddings.EmbeddingUnavailable):
            index.embed(["alpha stem"])

    def test_malformed_response_raises_embedding_unavailable(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_embedder(monkeypatch, vector_for=lambda _text: [])
        index = embeddings.EmbeddingIndex.from_config(factory_env)
        with pytest.raises(embeddings.EmbeddingUnavailable):
            index.embed(["alpha stem"])

    def test_batch_writes_one_provenance_event(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.core import audit_jsonl as audit_store

        install_fake_embedder(monkeypatch)
        index = embeddings.EmbeddingIndex.from_config(factory_env)
        index.embed(["alpha stem", "beta stem"])

        events = [
            ev for ev in audit_store.tail(20) if ev.get("type") == "embedding_batch"
        ]
        assert len(events) == 1
        assert events[0]["component"] == "lsat_factory_intake"
        assert events[0]["computed"] == 2
        assert events[0]["bank_revision"] == embeddings.bank_revision()
        assert events[0]["model"] == embeddings.DEFAULT_EMBED_MODEL


class TestClosestByEmbedding:
    def _corpus(self, texts: Iterable[str]) -> list[tuple[str, str]]:
        return [(f"id-{i}", t) for i, t in enumerate(texts)]

    def test_finds_the_nearest_row(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vectors = {
            "target": [1.0, 0.0, 0.0],
            "near": [0.99, 0.1, 0.0],
            "far": [0.0, 0.0, 1.0],
        }
        install_fake_embedder(monkeypatch, vector_for=lambda t: vectors[t])
        index = embeddings.EmbeddingIndex.from_config(factory_env)
        source_id, score = embeddings.closest_by_embedding(
            "target", self._corpus(["far", "near"]), index
        )
        assert source_id == "id-1"
        assert score > 0.99

    def test_empty_corpus_scores_zero(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_embedder(monkeypatch)
        index = embeddings.EmbeddingIndex.from_config(factory_env)
        assert embeddings.closest_by_embedding("target", [], index) == ("", 0.0)
