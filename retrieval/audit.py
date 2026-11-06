import json
import logging
import sys
from collections import Counter

from dotenv import load_dotenv

from .catalog import CatalogError, load_catalog
from .config import load_settings
from .taxonomy import load_category_rules, read_taxonomy
from .sections import SECTION_CODES

logger = logging.getLogger(__name__)


def read_sections() -> list[dict]:
    path = load_settings().rules_path
    if path is None:
        raise CatalogError("Не задан DATA_DIR или RULES_PATH")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["rules"]


def section_number(section: dict) -> int:
    return int(section["id"])


def unmapped_sections(sections: list[dict]) -> list[int]:
    return [
        section_number(section)
        for section in sections
        if section_number(section) not in SECTION_CODES
    ]


def repeated_refs(sections: list[dict]) -> int:
    sections_by_ref: dict[str, set[int]] = {}
    for section in sections:
        for point in section.get("points") or []:
            sections_by_ref.setdefault(str(point["ref"]), set()).add(section_number(section))
    return sum(1 for owners in sections_by_ref.values() if len(owners) > 1)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()
    sections = read_sections()
    points = Counter(section_number(section) for section in sections
                     for _ in section.get("points") or [])
    unmapped = unmapped_sections(sections)
    sys.stdout.write(f"sections={len(sections)}\n")
    sys.stdout.write(f"points={sum(points.values())}\n")
    sys.stdout.write(f"unmapped_section_ids={unmapped}\n")
    sys.stdout.write(f"repeated_refs_between_sections={repeated_refs(sections)}\n")
    broken = [number for number in unmapped if points[number] > 0]
    try:
        catalog = load_catalog(load_settings().rules_path)
    except CatalogError as error:
        logger.error("%s", error)
        return 1
    sys.stdout.write(f"unique_cite_ids={len(catalog)}\n")
    taxonomy_path = load_settings().taxonomy_path
    categories = read_taxonomy(taxonomy_path).get("categories") or []
    listed = sum(len(category.get("rules") or []) for category in categories)
    resolved = sum(len(ids) for ids in load_category_rules(taxonomy_path, list(catalog)).values())
    sys.stdout.write(f"taxonomy_rules={listed} taxonomy_resolved={resolved}\n")
    if broken or len(catalog) != sum(points.values()):
        logger.error("Разделы с пунктами без кода или неуникальные cite_id")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
