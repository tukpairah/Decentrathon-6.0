import pytest

from retrieval.taxonomy import (
    TAXONOMY_SECTION_DEFAULTS,
    category_rule_rows,
    load_category_rules,
    resolve_taxonomy_rule,
)


@pytest.fixture
def ids(catalog) -> list:
    return list(catalog)


@pytest.fixture
def taxonomy_path(synthetic_rules):
    return synthetic_rules.parent / "taxonomy.json"


def test_defaults_table():
    assert TAXONOMY_SECTION_DEFAULTS.bare_ref_section == "ОП"
    assert TAXONOMY_SECTION_DEFAULTS.section_expansions == {
        "GZ": ("1.1", "1.2", "1.3", "1.4", "1.5"),
    }


@pytest.mark.parametrize("raw, expected", [
    ("2.1", ["2.1 ОП"]),
    ("2.2", ["2.2 ОП"]),
    ("1.2", []),
    ("GZ", ["1.2 GZ"]),
    ("gz", ["1.2 GZ"]),
    ("ЖБ 1.1", ["1.1 ЖБ"]),
    ("ЖБ1.2", ["1.2 ЖБ"]),
    ("1.2 ЖБ", ["1.2 ЖБ"]),
    ("2.1 GZ", ["2.1 GZ"]),
    ("ЖБ 7.7", []),
    ("9.9", []),
    ("ЖБ", []),
    ("", []),
])
def test_resolve_taxonomy_rule(ids, raw, expected):
    assert resolve_taxonomy_rule(raw, ids) == expected


def test_unresolved_rule_is_logged(ids, caplog):
    resolve_taxonomy_rule("9.9", ids)
    assert "9.9" in caplog.text


def test_category_rules(ids, taxonomy_path):
    assert load_category_rules(taxonomy_path, ids) == {
        "complaint.insult": ["2.1 ОП"],
        "complaint.cheat": ["2.2 ОП"],
        "complaint.dm": ["2.1 ОП", "1.2 GZ"],
        "complaint.invalid": ["1.1 ЖБ"],
    }


def test_rows_keep_source_reference(ids, taxonomy_path):
    rows = category_rule_rows(taxonomy_path, ids)
    assert ("complaint.dm", "GZ", "1.2 GZ") in rows
    assert ("complaint.invalid", "ЖБ 1.1", "1.1 ЖБ") in rows
    assert all(raw != "9.9 ОП" for _, raw, _ in rows)
    assert ("complaint.dm", "GZ", "2.1 GZ") not in rows


def test_missing_taxonomy(ids, tmp_path):
    assert load_category_rules(tmp_path / "absent.json", ids) == {}
    assert load_category_rules(None, ids) == {}
