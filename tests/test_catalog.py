import json
from pathlib import Path

import pytest

from retrieval.catalog import CatalogError, load_catalog


def write_rules(path: Path, sections: list) -> Path:
    path.write_text(json.dumps({"rules": sections}, ensure_ascii=False), encoding="utf-8")
    return path


def test_loads_points_and_skips_empty_section(catalog):
    assert len(catalog) == 7
    assert all(rule.section in {"ОП", "ЖБ", "GZ"} for rule in catalog.values())


def test_same_ref_in_different_sections_is_kept(catalog):
    assert catalog["2.1 ОП"].text != catalog["2.1 GZ"].text
    assert catalog["2.1 GZ"].ref == "2.1"
    assert catalog["2.1 GZ"].section == "GZ"


def test_cite_ids_are_unique(catalog):
    assert len(set(catalog)) == len(catalog)


def test_duplicate_cite_id_raises(tmp_path):
    point = {"ref": "1.1", "text": "x"}
    path = write_rules(tmp_path / "dup.json", [
        {"id": 30, "points": [point, point]},
    ])
    with pytest.raises(CatalogError, match="1.1 ОП"):
        load_catalog(path)


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(CatalogError, match="не найден"):
        load_catalog(tmp_path / "absent.json")


def test_invalid_json_raises(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(path)


def test_unknown_section_raises(tmp_path):
    path = write_rules(tmp_path / "rules.json", [{"id": 99, "points": [{"ref": "1", "text": "x"}]}])
    with pytest.raises(CatalogError, match="99"):
        load_catalog(path)


def test_trailing_dot_in_ref_is_cleaned(tmp_path):
    section = {"id": 30, "points": [{"ref": "2.1.", "text": "x"}]}
    path = write_rules(tmp_path / "rules.json", [section])
    assert list(load_catalog(path)) == ["2.1 ОП"]
