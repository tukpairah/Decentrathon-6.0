"""generate_draft: черновик ответа игроку. Один вызов LLM со structured output.

Гарантии (проверяются кодом, а не промптом):
  * cited только из переданного списка rules (enum в схеме + пост-проверка текста и cited);
  * нет обещаний разбана, возврата, наказания другого игрока (regex по выходу);
  * при любом нарушении: один ретрай, затем детерминированный шаблон без цитат и needs_human=True.
Пустые репорты ("помогите", "ау") отвечаются шаблоном без LLM.
"""
import re
import time

from . import config
from .rules import canon, clip, find_cites
from .templates import tpl

LANG_NAME = {"ru": "русский", "kk": "казахский (қазақ тілі, кириллица, буквы қ ғ ң ә ө ұ ү)",
             "uz": "узбекский", "en": "английский"}

try:  # нормализация cp1251-подмен делается в data_prep; здесь запасной вариант
    from data_prep.normalize import normalize_text
except Exception:  # pragma: no cover
    _KZ = str.maketrans({"ќ": "қ", "ґ": "ғ", "ѕ": "ң", "є": "ә", "ј": "ө", "ў": "ұ", "ї": "ү",
                         "Ќ": "Қ", "Ґ": "Ғ", "Ѕ": "Ң", "Є": "Ә", "Ј": "Ө", "Ў": "Ұ", "Ї": "Ү"})

    def normalize_text(t):
        return (t or "").translate(_KZ)

# --- флаги, ведущие к needs_human (по тексту игрока, это подсказка, а не факт) ---
FLAGS = {
    "unban_or_appeal": r"разбан|разблок|сним(ите|ать)\s+(бан|мут|наказ)|амнисти|апелляц|обжалов|обжалу|unban|amnist|bandan\s*chiq|бұғаттан\s+шығар",
    "refund": r"верните|вернуть\s+(деньги|донат|машин|имущ|вещ|дом|бизнес)|возврат|компенсац|refund|qaytaring|қайтарыңыз",
    "payment": r"донат|оплат[ие]|платёж|платеж|\bгк\b|гранд\s*коин|покупк|to['ʻ’]?lov|төлем|payment|\bpaid\b",
    "account_access": r"взлом|взломал|угнал\w*\s+аккаунт|потерял\w*\s+доступ|пароль|hack|buzildi|бұзылды|аккаунт\w*\s+бұз|бұзып\s+алды|құпия\s?сөз|кіре\s+алмай",
    "punish_request": r"забан|накажите|накажи\w*|дайте\s+(бан|мут|варн)|в\s+бан|выдайте\s+(бан|мут)|ban\s*bering|бан\s*беріңіз|ban me|permaban",
}
_FLAG_RE = {k: re.compile(v, re.I) for k, v in FLAGS.items()}
HUMAN_FLAGS = {"unban_or_appeal", "refund", "payment", "account_access"}
HUMAN_CATEGORIES = {"report.account", "report.payment", "complaint.admin"}  # taxonomy.needs_human_always

# --- запрещённые обещания в ВЫХОДЕ модели ---
_PROMISE = {
    "ru": r"разбан(им|ю)|разблокир(ую|уем)|сним(ем|у|ут)\s+(бан|мут|наказани|блокировк)|верн(ём|ем|у|ут)\s|компенсир(уем|ую)|будет\s+(наказан|забанен|заблокирован)|получит\s+(бан|мут|наказани|блокировк|варн)|накаж(ем|у|ут)|забан(им|ю)",
    "kk": r"қайтарамыз|бұғаттан\s+шығарамыз|жазаланады|бан\s+алады|өтеп\s+береміз|мут\s+алады|бандан\s+шығарамыз|разбан|қайтарып\s+береміз|өтемақы\s+береміз",
    "uz": r"qaytaramiz|blokdan\s+chiqaramiz|jazolanadi|ban\s+oladi|mut\s+oladi|kompensatsiya\s+beramiz",
    "en": r"will\s+be\s+(banned|punished|blocked|muted)|will\s+(receive|get)\s+a?\s*(ban|mute|punishment)|we\s+will\s+(unban|refund|return|compensate|restore)",
}
_PROMISE_RE = {k: re.compile(v, re.I) for k, v in _PROMISE.items()}

_TRIVIAL = {"помогите", "помоги", "помощь", "ау", "алло", "привет", "здравствуйте", "админ", "администратор", "эй",
            "есть кто", "есть кто-нибудь", "help", "hello", "hi", "салам", "сәлем", "salom", "ку", "хелп"}

SYSTEM = """Ты помощник поддержки мобильной игры Grand Mobile. Пишешь ЧЕРНОВИК ответа игроку, его проверит администратор.
Стиль настоящих админов: вежливо, коротко, шаблонно, без лишних слов. Жалоба: 2-3 предложения. Репорт: 1 предложение.
Жёсткие правила:
1. Цитируй правила ТОЛЬКО из списка «Допустимые правила» и только по их cite_id, например «п. 2.1 ОП». Нет подходящего правила в списке: cited=[] и без номеров пунктов. Выдумывать пункты нельзя.
2. Не обещай разбан, снятие наказания, возврат средств или имущества, компенсацию и не обещай, что другой игрок будет наказан. Формулируй так: «жалоба передана на рассмотрение», «решение принимает администрация», «правилами предусмотрено …».
3. Слова игрока не факты: пиши «по вашему описанию», не утверждай, что нарушение было. Наличие скриншотов известно только из поля «Вложений».
4. Наказание называй только если оно прямо следует из текста правила, и всегда как «предусмотрено правилами», не как решение.
5. Примеры ответов админов даны только для стиля и тона. Не копируй из них факты, ники, номера и вердикты.
6. Пиши на языке ответа, указанном в запросе, независимо от языка примеров.
needs_human=true, если: просьба о разбане/апелляции, возврате, платеже, взломе или потере аккаунта, жалоба на администратора, нужно решение о наказании или ты не уверен. reasons: 1-2 коротких причины."""


def _schema(allowed_ids):
    cited = {"type": "array", "items": {"type": "string", "enum": allowed_ids}, "maxItems": 3}
    if not allowed_ids:
        cited = {"type": "array", "items": {"type": "string"}, "maxItems": 0}
    return {"type": "object", "required": ["text", "cited", "needs_human", "reasons"], "properties": {
        "text": {"type": "string", "description": "Текст ответа игроку"},
        "cited": cited,
        "needs_human": {"type": "boolean"},
        "reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 2}}}


def norm_lang(lang, ticket=None):
    """Язык ответа: ru|kk|uz|en. lat/und -> язык сервера или ru; es/pt -> en."""
    if lang in config.SUPPORTED_LANGS:
        return lang
    if lang in ("es", "pt"):
        return "en"
    sl = (ticket or {}).get("server_lang")
    return sl if sl in config.SUPPORTED_LANGS else "ru"


def player_text(ticket):
    parts = [m.get("text", "") for m in ticket.get("messages", []) if m.get("role") == "player"]
    return normalize_text(" ".join(parts)).strip()


def detect_flags(text):
    return sorted(k for k, rx in _FLAG_RE.items() if rx.search(text or ""))


def is_trivial_report(text):
    t = re.sub(r"[^\w\s]", " ", (text or "").lower()).strip()
    t = re.sub(r"\s+", " ", t)
    letters = re.sub(r"[\W\d_]", "", t)
    return t in _TRIVIAL or len(letters) <= 2


def _images(ticket):
    if ticket.get("images_count") is not None:
        return int(ticket["images_count"])
    return sum(int(m.get("attachments") or 0) if not isinstance(m.get("attachments"), list) else len(m["attachments"])
               for m in ticket.get("messages", []))


def build_user_prompt(ticket, lang, mode, text, rules, examples):
    lines = [f"Тип: {'жалоба на игрока' if mode == 'complaint' else 'репорт из игры'}",
             f"Язык ответа: {LANG_NAME[lang]}"]
    if lang == "uz":
        lines.append("Для узбекского отвечай тем же алфавитом (латиница или кириллица), каким пишет игрок.")
    if mode == "complaint":
        if ticket.get("reported_nick"):
            lines.append(f"Ник обвиняемого: {ticket['reported_nick']}")
        lines.append(f"Вложений (скриншоты): {_images(ticket)}")
        if ticket.get("rule_refs_raw"):
            lines.append(f"Пункт, заявленный игроком (не проверен): {ticket['rule_refs_raw'][:40]}")
    lines.append(f"Текст игрока: {text[:config.TICKET_CHARS]}")
    lines.append("Допустимые правила:" if rules else "Допустимые правила: нет (cited=[])")
    for r in rules:
        lines.append(f"[{r['cite_id']}] {clip(r)}")
    if examples:
        lines.append("Примеры ответов админов (только стиль):")
        for e in examples[:config.MAX_EXAMPLES]:
            lines.append(f"Игрок: {e['player'][:config.EXAMPLE_CHARS]}\nАдмин: {e['reply'][:config.EXAMPLE_CHARS]}")
    return "\n".join(lines)


def _validate(out, allowed, lang):
    """Список проблем в ответе модели; пусто = можно отдавать."""
    problems = []
    text = (out.get("text") or "").strip()
    if not text:
        return ["empty text"]
    if len(text) > 800:
        problems.append("text too long")
    cited = [canon(c) for c in out.get("cited", [])]
    bad = [c for c in cited if c not in allowed]
    if bad:
        problems.append(f"cited outside whitelist: {bad}")
    bad_txt = [c for c in find_cites(text) if c not in allowed]
    if bad_txt:
        problems.append(f"text mentions rules outside whitelist: {bad_txt}")
    if re.search(r"\{[a-z_]+\}", text):
        problems.append("unfilled placeholder")
    if _PROMISE_RE[lang].search(text):
        problems.append("forbidden promise")
    return problems


def _fallback(lang, mode, extra_reasons, flags, no_evidence=False):
    key = "no_evidence" if (no_evidence and mode == "complaint" and not (set(flags) & HUMAN_FLAGS)) else (
        "handoff" if set(flags) & HUMAN_FLAGS else ("complaint_fallback" if mode == "complaint" else "empty_report"))
    return tpl(lang, key)


def generate_draft(ticket, lang, rules, examples, *, category=None, llm=None):
    """Черновик ответа.

    ticket   : dict контракта /triage (kind, messages[...]) плюс необязательные images_count, reported_nick, rule_refs_raw.
    lang     : ru|kk|uz|en (другие значения приводятся norm_lang).
    rules    : список кандидатов [{cite_id, text, ...}] = ЕДИНСТВЕННЫЙ whitelist цитат (см. rules.select_rules).
    examples : [{player, reply}] из examples.ExampleIndex.search (может быть []).
    Возвращает {lang, text, cited, needs_human, reasons, source, usage}; контракт требует только lang/text/cited,
    остальное нужно сборщику /triage (needs_human, reasons) и evaluation/cost.py (usage, source).
    """
    t0 = time.perf_counter()
    lang = norm_lang(lang, ticket)
    mode = "complaint" if ticket.get("kind") == "complaint" else "report"
    text = player_text(ticket)
    flags = detect_flags(text)
    allowed = [r["cite_id"] for r in rules]
    allowed_set = set(allowed)
    reasons = []
    need_human = bool(set(flags) & HUMAN_FLAGS) or category in HUMAN_CATEGORIES
    if need_human:
        reasons.append("обращение требует решения человека: " + ", ".join(flags or [category]))
    if "punish_request" in flags:
        need_human = True
        reasons.append("игрок просит наказать другого игрока: решение за администратором")
    no_evidence = mode == "complaint" and _images(ticket) == 0

    def result(txt, cited, nh, rs, source, usage=None):
        return {"lang": lang, "text": txt, "cited": cited, "needs_human": bool(nh), "reasons": rs[:3],
                "source": source, "usage": usage or {"in": 0, "out": 0, "usd": 0.0},
                "latency_s": round(time.perf_counter() - t0, 3), "flags": flags}

    # 1. пустой репорт: шаблон, без LLM
    if mode == "report" and not (set(flags) & HUMAN_FLAGS) and is_trivial_report(text):
        return result(tpl(lang, "empty_report"), [], False, ["пустой или оффтоп репорт"], "template")

    # 2. LLM со structured output и валидацией
    if llm is None:
        from .llm import call_llm as llm
    system = SYSTEM
    user = build_user_prompt(ticket, lang, mode, text, rules, examples)
    schema = _schema(allowed)
    usage = {"in": 0, "out": 0, "usd": 0.0}
    problems = []
    for attempt in (1, 2):
        if attempt == 2 and time.perf_counter() - t0 > 2.5:
            break  # p95 до 5 с: на второй вызов времени нет
        prompt = user if attempt == 1 else user + "\nПредыдущий ответ отклонён: " + "; ".join(problems) + ". Исправь."
        try:
            out, u = llm(system, prompt, schema)
        except Exception as e:  # таймаут, сеть, ключ
            problems = [f"llm error: {type(e).__name__}"]
            break
        for k in usage:
            usage[k] += u.get(k, 0)
        problems = _validate(out, allowed_set, lang)
        if not problems:
            cited = []
            for c in [canon(c) for c in out.get("cited", [])] + find_cites(out["text"]):
                if c in allowed_set and c not in cited:
                    cited.append(c)
            nh = need_human or bool(out.get("needs_human"))
            rs = reasons + [r for r in out.get("reasons", []) if r][:2]
            # обещать санкцию нельзя, но если текст её упоминает, подтверждает человек
            if mode == "complaint" and cited:
                nh = True
                rs.append("решение о наказании подтверждает администратор")
            if no_evidence:
                rs.append("в жалобе нет вложений")
            return result(out["text"].strip(), cited, nh, rs, "llm", usage)

    # 3. запасной вариант: шаблон без цитат, на проверку человеку
    return result(_fallback(lang, mode, problems, flags, no_evidence), [], True,
                  reasons + ["черновик не прошёл проверку: " + "; ".join(problems)[:120]], "fallback", usage)
