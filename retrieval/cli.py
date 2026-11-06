import argparse
import logging
import sys
from typing import Optional, Sequence

from dotenv import load_dotenv

from .catalog import CatalogError
from .rules_index import get_index

logger = logging.getLogger(__name__)

TOP_K = 5
PREVIEW_LENGTH = 80


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m retrieval.cli")
    parser.add_argument("query")
    query = parser.parse_args(argv).query
    try:
        rules = get_index().search(query, TOP_K)
    except CatalogError as error:
        logger.error("%s", error)
        return 1
    for rule in rules:
        preview = rule.text[:PREVIEW_LENGTH].replace("\n", " ")
        sys.stdout.write(f"{rule.cite_id}\t{preview}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
