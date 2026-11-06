import pytest
from fastapi.testclient import TestClient

from app import interfaces
from app.main import app
from app.pipeline import SAFE_TEXT, triage
from app.schemas import DraftReply, Extracted, Message, TriageRequest
from retrieval import guards

PLAYER_TEXT = "Игрок оскорблял меня в чате, прикладываю видео"


def make_request(text: str = PLAYER_TEXT) -> TriageRequest:
    return TriageRequest(kind="complaint", messages=[Message(role="player", text=text)])


def stub_draft(monkeypatch: pytest.MonkeyPatch, text: str, cited: list) -> None:
    def fake_draft(req, lang, rules):
        return DraftReply(lang=lang, text=text, cited=cited)

    monkeypatch.setattr(interfaces, "generate_draft", fake_draft)


def test_invented_citation_falls_back_to_safe_text(monkeypatch):
    stub_draft(monkeypatch, "Нарушен пункт 9.9 ОП, игрок будет проверен", ["9.9 ОП"])
    response = triage(make_request())
    assert response.needs_human is True
    assert response.draft_reply.cited == []
    assert response.draft_reply.text == SAFE_TEXT
    assert "цитата не прошла проверку" in response.reasons


def test_invented_mention_in_text_falls_back_to_safe_text(monkeypatch):
    stub_draft(monkeypatch, "Мы проверим по пункту 9.9 общих правил", ["2.1 ОП"])
    response = triage(make_request())
    assert response.needs_human is True
    assert response.draft_reply.cited == []
    assert response.draft_reply.text == SAFE_TEXT


def test_valid_citation_is_canonicalized(monkeypatch):
    stub_draft(monkeypatch, "Проверим обращение по пункту 2.1 ОП.", ["2.1 OP", "п. 2.1 ОП"])
    response = triage(make_request())
    assert response.draft_reply.cited == ["2.1 ОП"]
    assert response.draft_reply.text != SAFE_TEXT


def test_player_text_reaches_guard(monkeypatch):
    stub_draft(monkeypatch, "Проверим обращение.", [])
    response = triage(make_request("Мой аккаунт взломали, оскорбляли в чате"))
    assert guards.REASON_ACCOUNT_TOPIC in response.reasons
    assert response.needs_human is True


def test_always_human_reason_is_not_duplicated(monkeypatch):
    stub_draft(monkeypatch, "Проверим обращение.", [])
    monkeypatch.setattr(interfaces, "classify", lambda req: ("report.payment", "p1", 0.9))
    response = triage(make_request())
    assert response.reasons.count(guards.REASON_ALWAYS_HUMAN) == 1


def test_missing_rules_file_degrades_to_empty_retrieval(monkeypatch, tmp_path):
    monkeypatch.setenv("RULES_PATH", str(tmp_path / "absent.json"))
    assert interfaces.retrieve("оскорбляет", 5) == []


def test_lifespan_warms_up_index():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_pipeline_passes_category_and_ref_hints(monkeypatch):
    seen: list = []

    def capture_draft(req, lang, rules):
        seen.extend(rule.cite_id for rule in rules)
        return DraftReply(lang=lang, text="Проверим обращение.", cited=[])

    monkeypatch.setattr(interfaces, "generate_draft", capture_draft)
    monkeypatch.setattr(interfaces, "classify", lambda req: ("complaint.cheat", "p2", 0.9))
    monkeypatch.setattr(
        interfaces, "extract_facts", lambda req: Extracted(rule_refs=["1.1 ЖБ"])
    )
    triage(make_request("qwertyuiop"))
    assert set(seen) == {"2.2 ОП", "1.1 ЖБ"}


def test_extracted_rule_refs_reach_retrieval(monkeypatch):
    calls: list = []
    original_retrieve = interfaces.retrieve

    def capture_retrieve(query, k=5, category=None, ref_hints=None):
        calls.append(list(ref_hints or []))
        return original_retrieve(query, k, category, ref_hints)

    monkeypatch.setattr(interfaces, "retrieve", capture_retrieve)
    stub_draft(monkeypatch, "Проверим обращение.", [])
    response = triage(make_request("qwertyuiop нарушен пункт 2.2 ОП"))
    assert "2.2 ОП" in response.extracted.rule_refs
    assert calls == [response.extracted.rule_refs]


def test_tests_do_not_call_live_llm(monkeypatch):
    from drafts import llm

    def forbidden(*args, **kwargs):
        raise AssertionError("live LLM call in tests")

    monkeypatch.setattr(llm, "_request", forbidden)
    response = triage(make_request())
    assert response.draft_reply.text


def test_failed_llm_draft_goes_to_human(monkeypatch):
    from drafts import adapter

    def broken_llm(system, user, schema):
        raise TimeoutError("slow")

    def draft_with_broken_llm(req, lang, rules):
        return adapter.generate_draft(req, lang, rules, llm=broken_llm, examples_index=False)

    monkeypatch.setattr(interfaces, "generate_draft", draft_with_broken_llm)
    monkeypatch.setattr(interfaces, "classify", lambda req: ("complaint.insult", "p2", 0.9))
    response = triage(make_request())
    assert response.needs_human is True
    assert adapter.NOT_GENERATED in response.reasons
    assert not any(reason.startswith("черновик не прошёл проверку") for reason in response.reasons)


def test_signals_do_not_leak_between_requests(monkeypatch):
    from drafts import adapter

    adapter._signals.set({"needs_human": True, "reasons": [adapter.NOT_GENERATED], "source": "fallback"})
    stub_draft(monkeypatch, "Проверим обращение.", [])
    monkeypatch.setattr(interfaces, "classify", lambda req: ("complaint.insult", "p2", 0.9))
    assert adapter.NOT_GENERATED not in triage(make_request()).reasons


def test_without_api_key_template_mode_does_not_raise_needs_human(monkeypatch):
    from drafts import adapter

    def draft_without_key(req, lang, rules):
        return adapter.generate_draft(req, lang, rules, examples_index=False)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(interfaces, "generate_draft", draft_without_key)
    monkeypatch.setattr(interfaces, "classify", lambda req: ("complaint.insult", "p2", 0.9))
    response = triage(make_request())
    assert adapter.NOT_GENERATED not in response.reasons
    assert response.needs_human is False
    assert response.draft_reply.text


def test_with_api_key_llm_error_goes_to_human(monkeypatch):
    from drafts import adapter, llm

    def failing_request(*args, **kwargs):
        raise TimeoutError("slow")

    def draft_with_key(req, lang, rules):
        return adapter.generate_draft(req, lang, rules, examples_index=False)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(llm, "_request", failing_request)
    monkeypatch.setattr(llm, "_limiter", llm.RateLimiter(0))
    monkeypatch.setattr(interfaces, "generate_draft", draft_with_key)
    monkeypatch.setattr(interfaces, "classify", lambda req: ("complaint.insult", "p2", 0.9))
    response = triage(make_request())
    assert adapter.NOT_GENERATED in response.reasons
    assert response.needs_human is True
