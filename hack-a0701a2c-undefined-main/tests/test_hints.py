from pathlib import Path

from retrieval.hints import resolve_hints
from retrieval.rules_index import RulesIndex, get_index

UNRELATED_QUERY = "qwertyuiop"


def found_ids(index: RulesIndex, query: str, **hints) -> list[str]:
    return [rule.cite_id for rule in index.search(query, 5, **hints)]


def test_resolve_hints_checks_catalog(catalog):
    ids = list(catalog)
    assert resolve_hints(["1.2 JB, 9.9 ОП", "2.1", "", "3.1ОП"], ids) == ["1.2 ЖБ", "3.1 ОП"]
    assert resolve_hints(["2.2 и 1.1"], ids) == ["2.2 ОП", "1.1 ЖБ"]


def test_ref_hint_adds_candidate_without_text_match(index):
    assert found_ids(index, UNRELATED_QUERY, ref_hints=["1.2 ЖБ"]) == ["1.2 ЖБ"]


def test_invented_ref_hint_is_ignored(index):
    assert found_ids(index, UNRELATED_QUERY, ref_hints=["9.9 ОП", "мусор"]) == []


def test_hints_are_fused_with_text_search(index):
    found = found_ids(index, "оскорбляет в чате", ref_hints=["1.2 ЖБ"])
    assert set(found[:2]) == {"2.1 ОП", "1.2 ЖБ"}


def test_category_hint_from_taxonomy(synthetic_rules: Path):
    index = get_index()
    assert found_ids(index, UNRELATED_QUERY, category="complaint.cheat") == ["2.2 ОП"]
    assert found_ids(index, UNRELATED_QUERY, category="complaint.invalid") == ["1.1 ЖБ"]
    assert found_ids(index, UNRELATED_QUERY, category="unknown") == []


def test_hints_work_with_empty_query(index):
    assert found_ids(index, "", ref_hints=["2.2"]) == ["2.2 ОП"]
