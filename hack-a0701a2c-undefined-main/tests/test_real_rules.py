import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from retrieval.catalog import load_catalog
from retrieval.rules_index import RulesIndex

EXPECTED_POINTS = 266

load_dotenv()


@pytest.fixture(scope="module")
def real_catalog() -> dict:
    data_dir = os.environ.get("DATA_DIR", "").strip()
    path = Path(data_dir) / "rules.json" if data_dir else None
    if path is None or not path.is_file():
        pytest.skip("DATA_DIR/rules.json недоступен")
    return load_catalog(path)


def test_point_count_and_unique_ids(real_catalog):
    assert len(real_catalog) == EXPECTED_POINTS
    assert len({rule.cite_id for rule in real_catalog.values()}) == EXPECTED_POINTS


def test_known_citations_exist(real_catalog):
    assert "2.1 ОП" in real_catalog
    assert "1.2 GZ" in real_catalog


def test_bm25_search_returns_known_rules(real_catalog, tmp_path):
    index = RulesIndex(real_catalog, False, "unused-model", tmp_path)
    assert len(index.search("2.1 ОП", 5)) > 0
