import types as pytypes

import pytest

from app import usage
from drafts import config, llm


class FakeError(Exception):
    def __init__(self, code, status, details=""):
        super().__init__(details or status)
        self.code, self.status, self.details = code, status, details


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def generate_content(self, model, contents, config):
        self.calls.append(config)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(text, tokens_in=120, tokens_out=30, thoughts=0):
    meta = pytypes.SimpleNamespace(prompt_token_count=tokens_in, candidates_token_count=tokens_out,
                                   thoughts_token_count=thoughts)
    return pytypes.SimpleNamespace(text=text, usage_metadata=meta)


@pytest.fixture
def fake_client(monkeypatch):
    def install(outcomes):
        models = FakeModels(outcomes)
        monkeypatch.setattr(llm, "_client", pytypes.SimpleNamespace(models=models))
        monkeypatch.setattr(llm, "_sleep", lambda s: None)
        monkeypatch.setattr(llm, "_limiter", llm.RateLimiter(0))
        return models
    return install


SCHEMA = {"type": "object", "properties": {"cited": {"type": "array", "items": {"type": "string", "enum": ["2.1 ОП"]}}}}


def test_returns_parsed_json_and_records_usage(fake_client, monkeypatch):
    monkeypatch.setattr(config, "PRICE_IN_PER_M", 1.0)
    monkeypatch.setattr(config, "PRICE_OUT_PER_M", 4.0)
    models = fake_client([response('{"text": "ok", "cited": ["2.1 ОП"]}', 1000, 100, 20)])
    usage.reset()
    data, used = llm.call_llm("sys", "user", SCHEMA)
    assert data == {"text": "ok", "cited": ["2.1 ОП"]}
    assert used == {"in": 1000, "out": 120, "usd": pytest.approx((1000 * 1.0 + 120 * 4.0) / 1e6)}
    assert usage.snapshot()["in"] == 1000 and usage.snapshot()["out"] == 120
    sent = models.calls[0]
    assert sent.response_json_schema == SCHEMA and sent.response_mime_type == "application/json"
    assert sent.thinking_config is None


def test_positive_thinking_budget_is_sent(fake_client, monkeypatch):
    monkeypatch.setattr(config, "THINKING_BUDGET", 128)
    models = fake_client([response('{"text": "ok"}')])
    llm.call_llm("sys", "user", SCHEMA)
    assert models.calls[0].thinking_config.thinking_budget == 128


def test_retries_on_429_then_succeeds(fake_client):
    models = fake_client([FakeError(429, "RESOURCE_EXHAUSTED", "retryDelay: '0.1s'"), response('{"text": "ok"}')])
    data, _ = llm.call_llm("sys", "user", SCHEMA)
    assert data == {"text": "ok"} and len(models.calls) == 2


def test_gives_up_after_max_attempts(fake_client):
    fake_client([FakeError(503, "UNAVAILABLE")] * llm.MAX_ATTEMPTS)
    with pytest.raises(FakeError):
        llm.call_llm("sys", "user", SCHEMA)


def test_does_not_retry_client_errors(fake_client):
    models = fake_client([FakeError(400, "INVALID_ARGUMENT"), response('{"text": "ok"}')])
    with pytest.raises(FakeError):
        llm.call_llm("sys", "user", SCHEMA)
    assert len(models.calls) == 1


def test_long_server_delay_falls_back_instead_of_waiting(fake_client):
    models = fake_client([FakeError(429, "RESOURCE_EXHAUSTED", "retryDelay: '37s'"), response('{"text": "ok"}')])
    with pytest.raises(FakeError):
        llm.call_llm("sys", "user", SCHEMA)
    assert len(models.calls) == 1


class FakeClock:
    def __init__(self):
        self.now, self.slept = 100.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 3))
        self.now += seconds


def test_rate_limiter_spaces_calls():
    clock = FakeClock()
    limiter = llm.RateLimiter(12, clock=clock, sleep=clock.sleep)
    assert limiter.acquire() and limiter.acquire() and limiter.acquire()
    assert clock.slept == [5.0, 5.0]


def test_rate_limiter_refuses_when_slot_is_too_far():
    clock = FakeClock()
    limiter = llm.RateLimiter(12, clock=clock, sleep=clock.sleep)
    assert limiter.acquire(max_wait=5)
    assert not limiter.acquire(max_wait=4.9)
    assert limiter.acquire(max_wait=5.0)
    assert clock.slept == [5.0]


def test_interactive_call_without_slot_times_out(fake_client, monkeypatch):
    models = fake_client([response('{"text": "ok"}')])
    busy = llm.RateLimiter(1)
    busy.acquire()
    monkeypatch.setattr(llm, "_limiter", busy)
    with pytest.raises(TimeoutError):
        llm.call_llm("sys", "user", SCHEMA)
    assert models.calls == []


def test_batch_mode_waits_for_slot(fake_client, monkeypatch):
    models = fake_client([response('{"text": "ok"}')])
    clock = FakeClock()
    busy = llm.RateLimiter(1, clock=clock, sleep=clock.sleep)
    busy.acquire()
    monkeypatch.setattr(llm, "_limiter", busy)
    monkeypatch.setattr(llm, "_batch_mode", True)
    data, _ = llm.call_llm("sys", "user", SCHEMA)
    assert data == {"text": "ok"} and clock.slept == [60.0] and len(models.calls) == 1


def test_empty_response_raises_but_tokens_are_recorded(fake_client):
    fake_client([response("", 500, 0)])
    usage.reset()
    with pytest.raises(ValueError, match="пустой"):
        llm.call_llm("sys", "user", SCHEMA)
    assert usage.snapshot()["in"] == 500


def test_empty_response_gives_fallback_draft(fake_client, monkeypatch):
    from drafts.generate import generate_draft

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    fake_client([response("", 400, 0), response("", 400, 0)])
    usage.reset()
    ticket = {"kind": "complaint", "messages": [{"role": "player", "text": "Игрок оскорблял меня в чате"}]}
    rules = [{"cite_id": "2.1 ОП", "text": "Запрещены оскорбления."}]
    result = generate_draft(ticket, "ru", rules, [], llm=llm.call_llm)
    assert result["source"] == "fallback"
    assert usage.snapshot()["in"] >= 400


@pytest.mark.parametrize("env, expected", [
    ({"GEMINI_API_KEY": "main", "LLM_API_KEY": "spare"}, "main"),
    ({"LLM_API_KEY": "spare"}, "spare"),
    ({"GEMINI_API_KEY": "  "}, ""),
    ({}, ""),
])
def test_api_key_prefers_gemini(monkeypatch, env, expected):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert config.api_key() == expected


def test_adapter_and_llm_agree_on_spare_key(monkeypatch):
    from drafts import adapter

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "spare")
    assert adapter.llm_configured() is True
    monkeypatch.delenv("LLM_API_KEY")
    assert adapter.llm_configured() is False
