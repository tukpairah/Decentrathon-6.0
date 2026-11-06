from typing import Iterable, Sequence

from .citations import resolve_citation, split_citations


def resolve_hints(raw_hints: Iterable[str], catalog_ids: Sequence[str]) -> list[str]:
    pieces = (piece for raw in raw_hints if raw for piece in split_citations(raw))
    resolved = (resolve_citation(piece, catalog_ids) for piece in pieces)
    return list(dict.fromkeys(cite_id for cite_id in resolved if cite_id is not None))
