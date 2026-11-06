from drafts.adapter import draft_signals, reset_draft_signals
from retrieval.validator import canonicalize_citations, find_invalid_mentions

from . import interfaces as I
from .schemas import DraftReply, TriageRequest, TriageResponse

SAFE_TEXT = "Здравствуйте! Ваше обращение передано администратору."
REASON_BAD_CITATION = "цитата не прошла проверку"
REASON_BAD_MENTION = "в тексте упомянут пункт, которого нет среди цитат"
LOW_CONFIDENCE = 0.5
REASON_LOW_CONFIDENCE = "низкая уверенность"


def safe_draft(lang: str) -> DraftReply:
    return DraftReply(lang=lang, text=SAFE_TEXT, cited=[])


def check_draft(draft: DraftReply, lang: str, rules: list) -> tuple[DraftReply, list[str]]:
    if not I.validate_citations(draft.cited, rules):
        return safe_draft(lang), [REASON_BAD_CITATION]
    cited = canonicalize_citations(draft.cited, rules)
    if find_invalid_mentions(draft.text, cited):
        return safe_draft(lang), [REASON_BAD_MENTION]
    return draft.model_copy(update={"cited": cited}), []


def draft_reasons() -> list[str]:
    signals = draft_signals()
    return list(signals["reasons"]) if signals["needs_human"] else []


def triage(req: TriageRequest) -> TriageResponse:
    text = " ".join(m.text for m in req.messages if m.role != "admin")
    lang = I.detect_lang(text)
    category, priority, confidence = I.classify(req)
    extracted = I.extract_facts(req)
    spam = I.is_spam_or_duplicate(req)

    rules = I.retrieve(text, k=5, category=category, ref_hints=extracted.rule_refs)
    reset_draft_signals()
    generated = I.generate_draft(req, lang, rules)
    draft, reasons = check_draft(generated, lang, rules)
    reasons += draft_reasons()
    reasons += I.needs_human_guard(category, draft.text, text)
    if confidence < LOW_CONFIDENCE:
        reasons.append(REASON_LOW_CONFIDENCE)

    reasons = list(dict.fromkeys(reasons))
    return TriageResponse(
        lang=lang, category=category, priority=priority,
        is_spam_or_duplicate=spam, extracted=extracted, draft_reply=draft,
        needs_human=bool(reasons), confidence=confidence, reasons=reasons,
    )
