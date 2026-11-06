from typing import Sequence

from .citations import find_mentions, resolve_citation
from .models import Citation, Rule, make_cite_id, ref_of


def retrieved_ids(retrieved: Sequence[Rule]) -> list[str]:
    return [rule.cite_id for rule in retrieved]


def validate_citations(cited: Sequence[str], retrieved: Sequence[Rule]) -> bool:
    allowed = retrieved_ids(retrieved)
    return all(resolve_citation(raw, allowed) is not None for raw in cited)


def canonicalize_citations(cited: Sequence[str], retrieved: Sequence[Rule]) -> list[str]:
    allowed = retrieved_ids(retrieved)
    resolved = (resolve_citation(raw, allowed) for raw in cited)
    return list(dict.fromkeys(cite_id for cite_id in resolved if cite_id is not None))


def find_invalid_mentions(text: str, cited_ids: Sequence[str]) -> list[str]:
    cited = set(cited_ids)
    refs = {ref_of(cite_id) for cite_id in cited}
    invalid = [
        mention.label
        for mention in find_mentions(text)
        if not is_cited(mention, cited, refs)
    ]
    return list(dict.fromkeys(invalid))


def is_cited(mention: Citation, cited: set[str], refs: set[str]) -> bool:
    if mention.code is None:
        return mention.ref in refs
    return make_cite_id(mention.ref, mention.code) in cited
