import logging
from typing import Optional, Sequence

from retrieval import guards, validator
from retrieval.catalog import CatalogError
from retrieval.models import Rule
from retrieval.rules_index import get_index

from .schemas import DraftReply, Extracted, TriageRequest

logger = logging.getLogger(__name__)


def detect_lang(text: str) -> str:
    return "ru"


def classify(req: TriageRequest) -> tuple[str, str, float]:
    from data_prep.classifier import classify as _classify

    return _classify(req)


def extract_facts(req: TriageRequest) -> Extracted:
    from data_prep.classifier import extract_facts as _extract_facts

    return _extract_facts(req)


def is_spam_or_duplicate(req: TriageRequest) -> bool:
    from data_prep.classifier import is_spam_or_duplicate as _is_spam_or_duplicate

    return _is_spam_or_duplicate(req)


def retrieve(
    query: str,
    k: int = 5,
    category: Optional[str] = None,
    ref_hints: Optional[Sequence[str]] = None,
) -> list[Rule]:
    try:
        return get_index().search(query, k, category, ref_hints or ())
    except CatalogError as error:
        logger.warning("Правила недоступны, поиск вернул пустой список: %s", error)
        return []


def validate_citations(cited: list[str], rules: list[Rule]) -> bool:
    return validator.validate_citations(cited, rules)


def needs_human_guard(category: str, draft_text: str, player_text: str = "") -> list[str]:
    return guards.needs_human_guard(category, draft_text, player_text)


def generate_draft(req: TriageRequest, lang: str, rules: list[Rule]) -> DraftReply:
    from drafts.adapter import generate_draft as _generate_draft

    return _generate_draft(req, lang, rules)
