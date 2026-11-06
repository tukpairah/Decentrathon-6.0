from retrieval.models import Rule
from retrieval.validator import canonicalize_citations, find_invalid_mentions, validate_citations


def make_rule(cite_id: str) -> Rule:
    ref, section = cite_id.split(" ")
    return Rule(cite_id=cite_id, section=section, ref=ref, text="synthetic")


RETRIEVED = [make_rule("2.1 ОП"), make_rule("1.2 ЖБ")]


def test_existing_citation_passes():
    assert validate_citations(["2.1 ОП"], RETRIEVED)
    assert validate_citations(["2.1 OP", "1.2 JB"], RETRIEVED)
    assert validate_citations([], RETRIEVED)


def test_invented_citation_fails():
    assert not validate_citations(["9.9 ОП"], RETRIEVED)
    assert not validate_citations(["2.1 ОП", "9.9 ОП"], RETRIEVED)
    assert not validate_citations(["мусор"], RETRIEVED)


def test_catalog_rule_not_found_by_search_fails(catalog):
    assert "2.1 GZ" in catalog
    assert not validate_citations(["2.1 GZ"], RETRIEVED)


def test_bare_ref_only_when_unambiguous():
    assert validate_citations(["1.2"], RETRIEVED)
    ambiguous = RETRIEVED + [make_rule("2.1 GZ")]
    assert not validate_citations(["2.1"], ambiguous)
    assert validate_citations(["2.1"], RETRIEVED)


def test_canonicalize_removes_duplicates_and_unresolved():
    cited = ["2.1 OP", "2.1ОП", "п. 2.1 ОП", "9.9 ОП", "1.2", "мусор"]
    assert canonicalize_citations(cited, RETRIEVED) == ["2.1 ОП", "1.2 ЖБ"]


def test_invalid_mention_in_text_is_caught():
    assert find_invalid_mentions("Нарушен пункт 9.9, наказание неизбежно", ["2.1 ОП"]) == ["9.9"]
    assert find_invalid_mentions("См. п. 9.9 ОП", ["2.1 ОП"]) == ["9.9 ОП"]


def test_cited_mentions_are_accepted():
    text = "По пункту 2.1 общих правил и п. 1.2 ЖБ"
    assert find_invalid_mentions(text, ["2.1 ОП", "1.2 ЖБ"]) == []


def test_mention_with_wrong_section_is_invalid():
    assert find_invalid_mentions("п. 2.1 ЖБ", ["2.1 ОП"]) == ["2.1 ЖБ"]


def test_text_without_mentions_is_clean():
    assert find_invalid_mentions("Здравствуйте! Обращение принято.", []) == []
