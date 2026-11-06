import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .citations import NUMBER, WORD, normalize_code, parse_citation
from .models import make_cite_id

logger = logging.getLogger(__name__)

CODE_FIRST = re.compile(rf"^\s*({WORD})\s*({NUMBER})\.?\s*$")


@dataclass(frozen=True)
class TaxonomyDefaults:
    bare_ref_section: str
    section_expansions: dict[str, tuple[str, ...]]


TAXONOMY_SECTION_DEFAULTS = TaxonomyDefaults(
    bare_ref_section="ОП",
    section_expansions={"GZ": ("1.1", "1.2", "1.3", "1.4", "1.5")},
)


def candidate_ids(raw: str, catalog_ids: Sequence[str]) -> list[str]:
    code = normalize_code(raw)
    if code in TAXONOMY_SECTION_DEFAULTS.section_expansions:
        refs = TAXONOMY_SECTION_DEFAULTS.section_expansions[code]
        return [make_cite_id(ref, code) for ref in refs]
    code_first = CODE_FIRST.match(raw)
    if code_first and normalize_code(code_first.group(1)):
        return [make_cite_id(code_first.group(2), normalize_code(code_first.group(1)))]
    parsed = parse_citation(raw)
    if parsed is None:
        return []
    section = parsed.code or TAXONOMY_SECTION_DEFAULTS.bare_ref_section
    return [make_cite_id(parsed.ref, section)]


def resolve_taxonomy_rule(raw: str, catalog_ids: Sequence[str]) -> list[str]:
    known = set(catalog_ids)
    resolved = [cite_id for cite_id in candidate_ids(raw, catalog_ids) if cite_id in known]
    if not resolved:
        logger.warning("Ссылка таксономии не разрешена и отброшена: %s", raw)
    return resolved


def read_taxonomy(path: Optional[Path]) -> dict:
    if path is None or not path.is_file():
        logger.warning("Таксономия не найдена, подсказки по категориям отключены: %s", path)
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        logger.warning("Не удалось прочитать таксономию %s: %s", path, error)
        return {}


def category_rule_rows(
    path: Optional[Path], catalog_ids: Sequence[str]
) -> list[tuple[str, str, str]]:
    return [
        (category["code"], str(raw), cite_id)
        for category in read_taxonomy(path).get("categories") or []
        if category.get("code")
        for raw in category.get("rules") or []
        for cite_id in resolve_taxonomy_rule(str(raw), catalog_ids)
    ]


def load_category_rules(path: Optional[Path], catalog_ids: Sequence[str]) -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {}
    for category in read_taxonomy(path).get("categories") or []:
        if category.get("code"):
            rules[category["code"]] = []
    for code, _, cite_id in category_rule_rows(path, catalog_ids):
        if cite_id not in rules[code]:
            rules[code].append(cite_id)
    return rules
