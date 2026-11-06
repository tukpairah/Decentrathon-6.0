"""Тесты харнесса: python -m pytest tests/test_evaluation.py  (или запуск как скрипта)."""
from evaluation.citations import parse_cite
from evaluation.common import build_request
from evaluation.promises import find_promises
from evaluation.run_eval import contract_errors, macro_f1

T = {"ticket_id": "x", "kind": "complaint", "images_count": 2, "messages": [
    {"role": "player", "text": "оскорбил"}, {"role": "reported_player", "text": "это РП"},
    {"role": "admin", "text": "жалоба одобрена, мут 30 минут"}]}


def test_admin_text_never_sent():
    req = build_request(T)
    assert all(m["role"] != "admin" for m in req["messages"])
    assert "одобрена" not in str(req)
    assert req["messages"][0]["attachments"] == 2


def test_promises():
    assert "unban" in find_promises("Мы сделаем разбан вашего аккаунта")
    assert "refund" in find_promises("Мы вернём деньги за донат")
    assert "punish_other" in find_promises("Игрок получит мут на 30 минут")
    assert not find_promises("Здравствуйте! Обращение принято, ожидайте ответа.")


def test_cite_formats():
    assert parse_cite("ЖБ 1.1.2") == ("1.1.2", "ЖБ") == parse_cite("1.1.2 жб")
    assert parse_cite("нарушение 2.1 OP") == ("2.1", "ОП")


def test_macro_f1_and_contract():
    assert macro_f1(["a", "b"], ["a", "b"]) == 1.0
    assert macro_f1(["a", "a", "b", "b"], ["a", "a", "a", "a"]) < 0.5
    assert contract_errors({"lang": "ru"}, set())


def test_disputed_codes_are_flagged_not_fabricated(tmp_path):
    import json
    from evaluation.citations import check_existence, load_rules
    rules = {"rules": [{"id": 34, "category": "x", "points": [{"ref": "1.1", "text": "t"}]},
                       {"id": 30, "category": "y", "points": [{"ref": "2.1", "text": "t"}]}]}
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules), encoding="utf-8")
    R = load_rules(p)
    assert check_existence("1.1 ПГО", R)["exists"] and not check_existence("1.1 ПГО", R)["unconfirmed_code"]
    assert check_existence("1.1 ГО", R)["exists"] and check_existence("1.1 ГО", R)["unconfirmed_code"]
    assert not check_existence("9.9 ОП", R)["exists"]      # выдуманный пункт
    assert not check_existence("1.1 ОП", R)["exists"]      # пункт 1.1 есть в разделе 34, а не в ОП


def _err(code, status, details=""):
    from google.genai import errors
    return errors.APIError(code, {"error": {"code": code, "status": status, "message": "quota",
                                            "details": details or []}})


def test_judge_retries_on_429_then_succeeds():
    pytest = __import__("pytest")
    pytest.importorskip("google.genai")
    from evaluation.judge import call_with_retry
    calls, slept = [], []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise _err(429, "RESOURCE_EXHAUSTED",
                       [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}])
        return "ok"
    assert call_with_retry(fn, sleep=slept.append, log=lambda *_: None) == "ok"
    assert len(calls) == 3 and len(slept) == 2 and all(7 <= s <= 8.6 for s in slept)  # пауза от сервера


def test_judge_stops_on_daily_quota_and_raises_other_errors():
    pytest = __import__("pytest")
    pytest.importorskip("google.genai")
    from evaluation.judge import DailyQuotaExceeded, call_with_retry
    daily = _err(429, "RESOURCE_EXHAUSTED", [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}])
    with pytest.raises(DailyQuotaExceeded):
        call_with_retry(lambda: (_ for _ in ()).throw(daily), sleep=lambda s: None, log=lambda *_: None)
    with pytest.raises(Exception):  # 400 не повторяем
        call_with_retry(lambda: (_ for _ in ()).throw(_err(400, "INVALID_ARGUMENT")), sleep=lambda s: None)


def test_rate_limiter_and_parse():
    from evaluation.judge import RateLimiter, parse
    t = [0.0]; slept = []
    rl = RateLimiter(6, clock=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
    rl.wait(); rl.wait()
    assert slept and abs(slept[0] - 10) < 1e-9  # 6 RPM = раз в 10 с
    assert parse('{"x": 4, "y": 2, "why": "ok"}') == (4, 2, "ok")
    assert parse('{"x": 9, "y": 2}') is None and parse("мусор") is None


def test_select_tickets_default_and_shuffle(tmp_path):
    import json

    from evaluation.run_eval import select_tickets

    path = tmp_path / "valid.jsonl"
    path.write_text("\n".join(json.dumps({"ticket_id": str(i)}) for i in range(20)), encoding="utf-8")
    first = [t["ticket_id"] for t in select_tickets(path, 5)]
    assert first == ["0", "1", "2", "3", "4"]
    shuffled = [t["ticket_id"] for t in select_tickets(path, 5, shuffle=True, seed=42)]
    assert shuffled == [t["ticket_id"] for t in select_tickets(path, 5, shuffle=True, seed=42)]
    assert shuffled != first and len(set(shuffled)) == 5
