"""Учёт токенов и стоимости одного запроса /triage (для evaluation/cost.py).

Каждый вызов LLM или эмбеддингов внутри запроса делает usage.record(...); эндпоинт отдаёт сумму
в заголовках X-Cost-Usd, X-Tokens-In, X-Tokens-Out. Контракт ответа (JSON) не меняется.
ContextVar изолирует запросы друг от друга, в том числе при параллельной нагрузке.
"""
from contextvars import ContextVar

_usage: ContextVar = ContextVar("triage_usage", default=None)


def reset() -> None:
    _usage.set({"in": 0, "out": 0, "usd": 0.0})


def record(tokens_in: int = 0, tokens_out: int = 0, usd: float = 0.0) -> None:
    u = _usage.get()
    if u is not None:
        u["in"] += tokens_in
        u["out"] += tokens_out
        u["usd"] += usd


def snapshot() -> dict:
    return dict(_usage.get() or {"in": 0, "out": 0, "usd": 0.0})
