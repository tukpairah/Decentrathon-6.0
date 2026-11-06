"""Адаптер под каркас /triage (app/interfaces.py): generate_draft(req, lang, rules) -> DraftReply.

Принимает pydantic-объекты каркаса (TriageRequest, Rule), превращает их в формат drafts.generate
и возвращает DraftReply. Правила = whitelist цитат: ровно то, что вернул retrieval у Рахата.
Примеры из train подключаются, если задан DATA_DIR; без них работает так же, но суше по тону.
"""
import os
from contextvars import ContextVar
from functools import lru_cache

from .generate import generate_draft as _generate


_signals: ContextVar = ContextVar("draft_signals", default=None)
NOT_GENERATED = "черновик не сгенерирован"


def reset_draft_signals():
    """Вызывать перед generate_draft в пайплайне: сигналы относятся только к текущему запросу."""
    _signals.set(None)


def draft_signals():
    """needs_human и reasons последнего черновика в этом запросе (контракт DraftReply их не содержит)."""
    return _signals.get() or {"needs_human": False, "reasons": [], "source": None}


def llm_configured(llm=None):
    """Без ключа (config.api_key) штатный режим шаблонов: fallback не считается ошибкой и не поднимает needs_human."""
    from . import config
    return llm is not None or bool(config.api_key())


def _signals_of(res, llm_enabled=True):
    if res.get("source") == "fallback":
        reasons = [r for r in res.get("reasons", []) if not r.startswith("черновик не прошёл проверку")]
        if not llm_enabled:
            return {"needs_human": bool(reasons), "reasons": reasons, "source": "template"}
        return {"needs_human": True, "reasons": [NOT_GENERATED] + reasons, "source": "fallback"}
    return {"needs_human": bool(res.get("needs_human")), "reasons": list(res.get("reasons", [])),
            "source": res.get("source")}


def rule_to_dict(rule):
    """Rule (retrieval.models) или dict -> {cite_id, text}. Имена полей подбираются устойчиво."""
    g = (lambda k: rule.get(k)) if isinstance(rule, dict) else (lambda k: getattr(rule, k, None))
    cite = g("cite_id") or g("cite") or g("citation")
    if not cite:
        ref, sec = g("ref") or g("point") or g("number"), g("section") or g("code")
        cite = f"{ref} {sec}".strip() if ref else None
    text = g("text") or g("body") or g("content") or ""
    if not cite:
        raise ValueError(f"не удалось определить cite_id у правила: {rule!r}")
    return {"cite_id": str(cite).strip(), "text": str(text)}


def req_to_ticket(req):
    msgs = [{"role": m.role, "text": m.text, "attachments": m.attachments} for m in req.messages]
    images = sum(m.attachments for m in req.messages if m.role != "admin")
    return {"kind": req.kind, "messages": msgs, "images_count": images}


@lru_cache(maxsize=1)
def get_examples():
    """Индекс примеров из train; None, если данных нет или DRAFT_EXAMPLES=0. Первый запуск строит кэш (~15 с)."""
    if os.environ.get("DRAFT_EXAMPLES", "1") == "0" or not os.environ.get("DATA_DIR"):
        return None
    try:
        from .examples import ExampleIndex
        return ExampleIndex.load()
    except Exception:
        return None


def warmup():
    """Вызвать при старте сервиса, чтобы первый запрос не ждал построения индекса."""
    return get_examples() is not None


def generate_draft(req, lang, rules, *, llm=None, examples_index=None, reply_cls=None):
    from .generate import player_text
    ticket = req_to_ticket(req)
    cand = [rule_to_dict(r) for r in rules]
    idx = examples_index if examples_index is not None else get_examples()
    ex = []
    if idx is not None:
        try:
            ex = idx.search(player_text(ticket), ticket["kind"], lang)
        except Exception:
            ex = []
    res = _generate(ticket, lang, cand, ex, llm=llm)
    _signals.set(_signals_of(res, llm_configured(llm)))
    if reply_cls is None:
        from app.schemas import DraftReply as reply_cls  # каркас Рахата
    return reply_cls(lang=res["lang"], text=res["text"], cited=res["cited"])
