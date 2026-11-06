import sys
import types

import numpy as np
import pytest

from retrieval.rules_index import RulesIndex, reciprocal_rank_fusion, tokenize


def test_finds_expected_rule(index):
    assert index.search("игрок оскорбляет в чате", 3)[0].cite_id == "2.1 ОП"
    assert index.search("прикрепить видео к жалобе", 3)[0].cite_id == "1.2 ЖБ"
    assert index.search("убивать игроков в безопасной области", 3)[0].cite_id == "2.1 GZ"


def test_empty_query_returns_nothing(index):
    assert index.search("") == []
    assert index.search("   ") == []


def test_query_without_matches_returns_nothing(index):
    assert index.search("qwertyuiop") == []


def test_k_larger_than_catalog(index, catalog):
    found = index.search("запрещено игроков жалобе области", 100)
    assert 0 < len(found) <= len(catalog)
    assert len({rule.cite_id for rule in found}) == len(found)


def test_non_positive_k(index):
    assert index.search("оскорбляет", 0) == []


def test_results_respect_k(index):
    assert len(index.search("запрещено", 2)) <= 2


def test_empty_catalog_index(tmp_path):
    empty = RulesIndex({}, False, "unused-model", tmp_path)
    assert empty.search("что угодно") == []


def test_embeddings_failure_falls_back_to_bm25(catalog, tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    fallback = RulesIndex(catalog, True, "missing-model", tmp_path)
    assert fallback.search("оскорбляет в чате", 1)[0].cite_id == "2.1 ОП"


def test_tokenize_stems_and_folds_yo():
    assert tokenize("Зелёная ЗОНА, 2.1") == ["зелен", "зона", "2", "1"]


def test_rank_fusion_prefers_agreement():
    assert reciprocal_rank_fusion([(1.0, [1, 2, 3]), (1.0, [2, 1, 4])])[:2] == [1, 2]


def test_rank_fusion_respects_weights():
    assert reciprocal_rank_fusion([(1.0, [1, 2]), (3.0, [2, 1])])[0] == 2


def test_hint_weight_lifts_hint_above_text_match(catalog, tmp_path):
    from retrieval.config import FusionWeights

    query = "оскорбляет в чате"
    plain = RulesIndex(catalog, False, "unused-model", tmp_path, None, FusionWeights(hints=1.0))
    boosted = RulesIndex(catalog, False, "unused-model", tmp_path, None, FusionWeights(hints=3.0))
    assert plain.search(query, 1, ref_hints=["1.2 ЖБ"])[0].cite_id == "2.1 ОП"
    assert boosted.search(query, 1, ref_hints=["1.2 ЖБ"])[0].cite_id == "1.2 ЖБ"


def test_weights_from_environment(monkeypatch):
    from retrieval.config import load_settings

    monkeypatch.setenv("RRF_WEIGHT_HINTS", "2.5")
    monkeypatch.setenv("RRF_WEIGHT_E5", "bad")
    weights = load_settings().weights
    assert (weights.bm25, weights.e5, weights.hints) == (1.0, 1.0, 2.5)


def test_default_weights(monkeypatch):
    from retrieval.config import load_settings

    for name in ("RRF_WEIGHT_BM25", "RRF_WEIGHT_E5", "RRF_WEIGHT_HINTS"):
        monkeypatch.delenv(name, raising=False)
    weights = load_settings().weights
    assert (weights.bm25, weights.e5, weights.hints) == (1.0, 1.0, 2.0)


class FakeEncoder:
    calls = 0

    def __init__(self, model_name):
        self.model_name = model_name

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        FakeEncoder.calls += 1
        vectors = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text.split(": ", 1)[-1]):
                vectors[row, hash(token) % 64] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-9)


@pytest.fixture
def fake_embeddings(monkeypatch):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    FakeEncoder.calls = 0


def test_hybrid_search_and_embedding_cache(fake_embeddings, catalog, tmp_path):
    cache_dir = tmp_path / "embeddings"
    first = RulesIndex(catalog, True, "fake-model", cache_dir)
    assert first.search("оскорбляет в чате", 1)[0].cite_id == "2.1 ОП"
    assert len(list(cache_dir.glob("embeddings-*.npz"))) == 1
    calls_after_first = FakeEncoder.calls
    second = RulesIndex(catalog, True, "fake-model", cache_dir)
    second.search("оскорбляет в чате", 1)
    assert FakeEncoder.calls == calls_after_first + 1


def test_cache_key_depends_on_model(fake_embeddings, catalog, tmp_path):
    RulesIndex(catalog, True, "model-a", tmp_path)
    RulesIndex(catalog, True, "model-b", tmp_path)
    assert len(list(tmp_path.glob("embeddings-*.npz"))) == 2
