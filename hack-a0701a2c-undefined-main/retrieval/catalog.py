import json
import logging
import re
from pathlib import Path
from typing import Union

from .models import Rule, make_cite_id
from .sections import SECTION_CODES

logger = logging.getLogger(__name__)

SECTION_NUMBER = re.compile(r"\d+")


class CatalogError(Exception):
    pass


def read_rules_file(path: Path) -> dict:
    if not path.is_file():
        raise CatalogError(f"Файл правил не найден: {path}")
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        raise CatalogError(f"Не удалось прочитать файл правил {path}: {error}") from error


def section_code(raw_id: object) -> str:
    found = SECTION_NUMBER.search(str(raw_id))
    code = SECTION_CODES.get(int(found.group())) if found else None
    if code is None:
        raise CatalogError(f"Неизвестный раздел правил с id={raw_id!r}")
    return code


def clean_ref(raw_ref: object) -> str:
    ref = str(raw_ref).strip().rstrip(".").strip()
    if not ref:
        raise CatalogError("В правилах найден пункт с пустым номером")
    return ref


def build_rules(section: dict) -> list[Rule]:
    points = section.get("points") or []
    if not points:
        logger.info("Раздел %s без пунктов пропущен", section.get("id"))
        return []
    code = section_code(section.get("id"))
    return [
        Rule(
            cite_id=make_cite_id(clean_ref(point.get("ref")), code),
            section=code,
            ref=clean_ref(point.get("ref")),
            text=str(point.get("text") or ""),
        )
        for point in points
    ]


def load_catalog(path: Union[str, Path]) -> dict[str, Rule]:
    payload = read_rules_file(Path(path))
    catalog: dict[str, Rule] = {}
    for section in payload.get("rules") or []:
        for rule in build_rules(section):
            if rule.cite_id in catalog:
                raise CatalogError(f"Повторяющийся идентификатор пункта: {rule.cite_id}")
            catalog[rule.cite_id] = rule
    if not catalog:
        raise CatalogError(f"В файле правил нет ни одного пункта: {path}")
    return catalog
