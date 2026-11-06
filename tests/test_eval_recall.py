from retrieval.eval_recall import evaluable_cases, query_text, sample_cases

IDS = ["2.1 ОП", "2.1 GZ", "1.2 ЖБ"]


def make_ticket(violation: object, verdict: str = "approved", kind: str = "complaint") -> dict:
    return {
        "kind": kind,
        "verdict": verdict,
        "violation": violation,
        "messages": [
            {"role": "player", "text": "игрок"},
            {"role": "reported_player", "text": "ответчик"},
            {"role": "admin", "text": "решение"},
        ],
    }


def test_query_excludes_admin():
    assert query_text(make_ticket("2.1 ОП")) == "игрок ответчик"


def test_only_approved_complaints_with_resolvable_violation():
    tickets = [
        make_ticket("2.1 OP"),
        make_ticket("2.1"),
        make_ticket("1.2"),
        make_ticket(None),
        make_ticket("2.1 ОП", verdict="rejected"),
        make_ticket("2.1 ОП", kind="report"),
    ]
    assert [target for _, target in evaluable_cases(tickets, IDS)] == ["2.1 ОП", "1.2 ЖБ"]


def test_sample_is_deterministic_and_limited():
    cases = [({"n": n}, "2.1 ОП") for n in range(100)]
    first = sample_cases(cases, 10)
    assert len(first) == 10
    assert first == sample_cases(cases, 10)
    assert sample_cases(cases, 0) == cases
    assert sample_cases(cases, 500) == cases
