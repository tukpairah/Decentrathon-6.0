import logging
import sys

from dotenv import load_dotenv

from .catalog import CatalogError
from .config import load_settings
from .rules_index import get_index
from .taxonomy import category_rule_rows

logger = logging.getLogger(__name__)

PREVIEW_LENGTH = 80


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    load_dotenv()
    try:
        index = get_index()
    except CatalogError as error:
        logger.error("%s", error)
        return 1
    rows = category_rule_rows(load_settings().taxonomy_path, index.cite_ids)
    for category, raw, cite_id in rows:
        preview = index.rule(cite_id).text[:PREVIEW_LENGTH].replace("\n", " ")
        sys.stdout.write(f"{category}\t{raw}\t{cite_id}\t{preview}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
