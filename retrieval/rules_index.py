import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from rank_bm25 import BM25Okapi

from .catalog import CatalogError, load_catalog
from .config import FusionWeights, load_settings
from .hints import resolve_hints
from .models import Rule
from .sections import SECTION_TITLES
from .taxonomy import load_category_rules

logger = logging.getLogger(__name__)

RRF_K = 60
STEM_LENGTH = 5
MAX_PASSAGE_TEXT = 1000
CANDIDATE_POOL = 50
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "
TOKEN_PATTERN = re.compile(r"\w+")
WARM_UP_QUERIES = (
    "оскорбление в чате",
    "использование читов",
    "убийство в зелёной зоне",
    "продажа аккаунта",
)


def tokenize(text: str) -> list[str]:
    words = TOKEN_PATTERN.findall(text.lower().replace("ё", "е"))
    return [word[:STEM_LENGTH] for word in words]


def build_passage(rule: Rule) -> str:
    title = SECTION_TITLES.get(rule.section, rule.section)
    return f"{title}. {rule.ref}. {rule.text[:MAX_PASSAGE_TEXT]}"


def reciprocal_rank_fusion(rankings: list[tuple[float, list[int]]]) -> list[int]:
    scores: dict[int, float] = {}
    for weight, ranking in rankings:
        for position, index in enumerate(ranking, start=1):
            scores[index] = scores.get(index, 0.0) + weight / (RRF_K + position)
    return sorted(scores, key=lambda index: (-scores[index], index))


def cache_key(model_name: str, rules: list[Rule], passages: list[str]) -> str:
    digest = hashlib.sha256(model_name.encode("utf-8"))
    for rule, passage in zip(rules, passages):
        digest.update(f"\n{rule.cite_id}\t{passage}".encode("utf-8"))
    return digest.hexdigest()[:24]


def top_indices(scores: np.ndarray) -> list[int]:
    order = np.argsort(-scores, kind="stable")[:CANDIDATE_POOL]
    return [int(index) for index in order]


class RulesIndex:
    def __init__(
        self,
        catalog: dict[str, Rule],
        use_embeddings: bool,
        model_name: str,
        cache_dir: Path,
        category_rules: Optional[dict[str, list[str]]] = None,
        weights: Optional[FusionWeights] = None,
    ) -> None:
        self._weights = weights or FusionWeights()
        self._rules = list(catalog.values())
        self._positions = {rule.cite_id: index for index, rule in enumerate(self._rules)}
        self._category_rules = category_rules or {}
        self._passages = [build_passage(rule) for rule in self._rules]
        corpus = [tokenize(passage) for passage in self._passages]
        self._bm25: Optional[BM25Okapi] = BM25Okapi(corpus) if corpus else None
        self._encoder = None
        self._vectors: Optional[np.ndarray] = None
        if use_embeddings and self._rules:
            self._enable_embeddings(model_name, Path(cache_dir))

    @property
    def cite_ids(self) -> list[str]:
        return [rule.cite_id for rule in self._rules]

    @property
    def taxonomy_ids(self) -> set[str]:
        return {cite_id for ids in self._category_rules.values() for cite_id in ids}

    def rule(self, cite_id: str) -> Rule:
        return self._rules[self._positions[cite_id]]

    @property
    def weights(self) -> FusionWeights:
        return self._weights

    @property
    def has_embeddings(self) -> bool:
        return self._vectors is not None

    def search(
        self,
        query: str,
        k: int = 5,
        category: Optional[str] = None,
        ref_hints: Sequence[str] = (),
    ) -> list[Rule]:
        if k <= 0 or not self._rules:
            return []
        category_ids = self._category_rules.get(category or "", [])
        rankings = [
            (self._weights.bm25, self._bm25_ranking(query)),
            (self._weights.e5, self._embedding_ranking(query)),
            (self._weights.hints, self._hint_ranking(category_ids)),
            (self._weights.hints, self._hint_ranking(resolve_hints(ref_hints, self.cite_ids))),
        ]
        fused = reciprocal_rank_fusion([pair for pair in rankings if pair[1]])
        return [self._rules[index] for index in fused[:k]]

    def _bm25_ranking(self, query: str) -> list[int]:
        tokens = tokenize(query)
        if not tokens or self._bm25 is None:
            return []
        scores = np.asarray(self._bm25.get_scores(tokens))
        return [index for index in top_indices(scores) if scores[index] > 0]

    def _hint_ranking(self, cite_ids: Sequence[str]) -> list[int]:
        return [self._positions[cite_id] for cite_id in cite_ids if cite_id in self._positions]

    def _embedding_ranking(self, query: str) -> list[int]:
        if self._encoder is None or self._vectors is None or not query.strip():
            return []
        try:
            vector = self._encode([QUERY_PREFIX + query])[0]
            return top_indices(self._vectors @ vector)
        except Exception as error:
            logger.warning("Поиск по эмбеддингам не удался, остаётся BM25: %s", error)
            return []

    def _encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._encoder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

    def _enable_embeddings(self, model_name: str, cache_dir: Path) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(model_name)
            self._vectors = self._load_or_encode(model_name, cache_dir)
        except Exception as error:
            logger.warning("Эмбеддинги недоступны, используется только BM25: %s", error)
            self._encoder = None
            self._vectors = None

    def _load_or_encode(self, model_name: str, cache_dir: Path) -> np.ndarray:
        path = cache_dir / f"embeddings-{cache_key(model_name, self._rules, self._passages)}.npz"
        cached = read_cached_vectors(path, len(self._rules))
        if cached is not None:
            return cached
        vectors = self._encode([PASSAGE_PREFIX + passage for passage in self._passages])
        write_cached_vectors(path, vectors)
        return vectors


def read_cached_vectors(path: Path, expected_rows: int) -> Optional[np.ndarray]:
    if not path.is_file():
        return None
    try:
        with np.load(path) as archive:
            vectors = archive["vectors"]
    except (OSError, ValueError, KeyError) as error:
        logger.warning("Кэш эмбеддингов повреждён и будет пересоздан: %s", error)
        return None
    return vectors if vectors.shape[0] == expected_rows else None


def write_cached_vectors(path: Path, vectors: np.ndarray) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, vectors=vectors)
    except OSError as error:
        logger.warning("Не удалось записать кэш эмбеддингов: %s", error)


_index: Optional[RulesIndex] = None
_index_lock = threading.Lock()


def get_index() -> RulesIndex:
    global _index
    with _index_lock:
        if _index is None:
            settings = load_settings()
            if settings.rules_path is None:
                raise CatalogError("Не задан путь к правилам: укажите DATA_DIR или RULES_PATH")
            catalog = load_catalog(settings.rules_path)
            _index = RulesIndex(
                catalog,
                settings.use_embeddings,
                settings.embedding_model,
                settings.cache_dir,
                load_category_rules(settings.taxonomy_path, list(catalog)),
                settings.weights,
            )
        return _index


def reset_index() -> None:
    global _index
    with _index_lock:
        _index = None


def warm_up_index() -> bool:
    try:
        index = get_index()
    except CatalogError as error:
        logger.warning("Индекс правил не прогрет: %s", error)
        return False
    for query in WARM_UP_QUERIES:
        index.search(query)
    return True
