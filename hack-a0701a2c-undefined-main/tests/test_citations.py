import pytest

from retrieval.citations import find_mentions, normalize_code, parse_citation, resolve_citation
from retrieval.models import Citation

CANDIDATES = ["2.1 ОП", "2.1 GZ", "1.2 ЖБ"]


@pytest.mark.parametrize("raw, expected", [
    ("ОП", "ОП"), ("оп", "ОП"), ("OP", "ОП"), ("op", "ОП"), ("JB", "ЖБ"), ("ZB", "ЖБ"),
    ("OП", "ОП"), ("CM", "СМ"), ("GZ", "GZ"), ("gz", "GZ"), ("ГЗ", "GZ"), ("ОПГ", "ОПГ"),
    (" ОП. ", "ОП"), ("XX", None), ("", None), ("???", None),
])
def test_normalize_code(raw, expected):
    assert normalize_code(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("2.1 ОП", ("2.1", "ОП")),
    ("2.1ОП", ("2.1", "ОП")),
    ("п. 2.1 ОП", ("2.1", "ОП")),
    ("нарушение 2.1 OP", ("2.1", "ОП")),
    ("1.2 gz", ("1.2", "GZ")),
    ("2.1", ("2.1", None)),
    ("п. 2.1", ("2.1", None)),
    ("2.1.", ("2.1", None)),
    ("2.1 нарушение правил", ("2.1", None)),
    ("2.1 ЯЯ", None),
    ("2.1 ОП и 3.1 ЖБ", None),
    ("", None),
    ("   ", None),
    ("ОП", None),
    ("мусор без номера", None),
])
def test_parse_citation(raw, expected):
    assert parse_citation(raw) == expected


def test_resolve_with_code():
    assert resolve_citation("2.1 OP", CANDIDATES) == "2.1 ОП"
    assert resolve_citation("2.1ОП", CANDIDATES) == "2.1 ОП"


def test_resolve_missing_code_in_candidates():
    assert resolve_citation("2.1 ЖБ", CANDIDATES) is None
    assert resolve_citation("9.9 ОП", CANDIDATES) is None


def test_resolve_bare_ref_requires_single_candidate():
    assert resolve_citation("2.1", CANDIDATES) is None
    assert resolve_citation("1.2", CANDIDATES) == "1.2 ЖБ"
    assert resolve_citation("5.5", CANDIDATES) is None


@pytest.mark.parametrize("raw", ["", "   ", "мусор", "ОП", "2.1 ОП 3.1 ЖБ", "!!!"])
def test_resolve_garbage(raw):
    assert resolve_citation(raw, CANDIDATES) is None


def test_resolve_accepts_generator():
    assert resolve_citation("1.2", (c for c in CANDIDATES)) == "1.2 ЖБ"


def test_find_mentions_formats():
    text = "Согласно пункту 2.1 общих правил и п. 1.2 ЖБ, а также п.3.4 и 4.5 GZ."
    assert find_mentions(text) == [
        Citation("2.1", "ОП"), Citation("1.2", "ЖБ"), Citation("3.4", None), Citation("4.5", "GZ"),
    ]


def test_find_mentions_ignores_plain_numbers_and_words():
    text = "Срок 7 дней, пример 3 и цена 1.5 раза. Дата 12.05.2024."
    assert find_mentions(text) == []


def test_find_mentions_deduplicates():
    assert find_mentions("п. 2.1 ОП и снова пункт 2.1 ОП") == [Citation("2.1", "ОП")]


def test_resolve_mixed_script_and_case():
    assert resolve_citation("2.1 OП", CANDIDATES) == "2.1 ОП"
    assert resolve_citation("2.1 oп", CANDIDATES) == "2.1 ОП"
    assert resolve_citation("1.2 жб", CANDIDATES) == "1.2 ЖБ"


def test_find_mentions_phrase_with_yo():
    assert find_mentions("по пункту 2.1 зелёной зоны") == [Citation("2.1", "GZ")]
    assert find_mentions("по ПУНКТУ 2.1 ЗЕЛЕНОЙ ЗОНЫ") == [Citation("2.1", "GZ")]


def test_find_mentions_lowercase_code_word_is_not_a_code():
    assert find_mentions("в пункте 5 го уровня") == [Citation("5", None)]
