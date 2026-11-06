import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_CACHE_DIR = ".cache"
RULES_FILE_NAME = "rules.json"
TAXONOMY_FILE_NAME = "taxonomy.json"
DISABLED_VALUES = frozenset({"off", "0", "false", "no"})


@dataclass(frozen=True)
class FusionWeights:
    bm25: float = 1.0
    e5: float = 1.0
    hints: float = 2.0


@dataclass(frozen=True)
class Settings:
    data_dir: Optional[Path]
    rules_path: Optional[Path]
    taxonomy_path: Optional[Path]
    use_embeddings: bool
    embedding_model: str
    cache_dir: Path
    weights: FusionWeights


def read_weight(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    try:
        return float(value) if value else default
    except ValueError:
        return default


def load_weights() -> FusionWeights:
    defaults = FusionWeights()
    return FusionWeights(
        bm25=read_weight("RRF_WEIGHT_BM25", defaults.bm25),
        e5=read_weight("RRF_WEIGHT_E5", defaults.e5),
        hints=read_weight("RRF_WEIGHT_HINTS", defaults.hints),
    )


def read_path(name: str) -> Optional[Path]:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


def load_settings() -> Settings:
    data_dir = read_path("DATA_DIR")
    rules_path = read_path("RULES_PATH")
    if rules_path is None and data_dir is not None:
        rules_path = data_dir / RULES_FILE_NAME
    taxonomy_path = read_path("TAXONOMY_PATH")
    if taxonomy_path is None and data_dir is not None:
        taxonomy_path = data_dir / TAXONOMY_FILE_NAME
    switch = os.environ.get("RETRIEVAL_EMBEDDINGS", "on").strip().lower()
    return Settings(
        data_dir=data_dir,
        rules_path=rules_path,
        taxonomy_path=taxonomy_path,
        use_embeddings=switch not in DISABLED_VALUES,
        embedding_model=os.environ.get("EMBEDDING_MODEL", "").strip() or DEFAULT_EMBEDDING_MODEL,
        cache_dir=read_path("CACHE_DIR") or Path(DEFAULT_CACHE_DIR),
        weights=load_weights(),
    )
