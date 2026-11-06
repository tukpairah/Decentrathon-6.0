"""Ticket language, normalization, weak labels, classification and fact extraction.
No remote services are needed. Optional trained sklearn model is loaded if present.
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path

from app.schemas import Extracted, TriageRequest

ROOT = Path(__file__).resolve().parent
TRAIN_FILE = 'tickets_train.jsonl.gz'
logger = logging.getLogger(__name__)


def model_path() -> Path:
    # Модель не хранится в репозитории: обучается из DATA_DIR при первом старте и лежит в кэше
    return Path(os.environ.get('CACHE_DIR') or ROOT.parent / '.cache') / 'classifier.joblib'


MODEL_PATH = model_path()
_model_cache: dict = {}


def load_model():
    path = model_path()
    if not path.exists():
        return None
    key = (str(path), path.stat().st_mtime)
    if key not in _model_cache:
        try:
            import joblib
            model = joblib.load(path)
        except (ImportError, OSError, ValueError, EOFError) as err:
            logger.warning('Не удалось загрузить модель classify %s: %s', path, err)
            return None
        _model_cache.clear()
        _model_cache[key] = model
    return _model_cache[key]


def ensure_model() -> bool:
    """Есть модель в кэше -> True. Нет, но есть DATA_DIR -> обучает (~12 с). Иначе правила и предупреждение."""
    path = model_path()
    if path.exists():
        return True
    data_dir = os.environ.get('DATA_DIR', '').strip()
    source = Path(data_dir) / TRAIN_FILE if data_dir else None
    if source is None or not source.exists():
        logger.warning('Модель classify не найдена и DATA_DIR/%s недоступен: работают только правила', TRAIN_FILE)
        return False
    from .train import train
    started = time.perf_counter()
    count = train(source, path)
    logger.info('Модель classify обучена на %d тикетах за %.1f с: %s', count, time.perf_counter() - started, path)
    return True

KEYWORDS = {
 'complaint.insult': ['оскорб', 'матер', 'обзыв', 'унижа', 'insult', 'ofensa', 'xingamento', 'оск родни', 'оскр родни', 'оскр', 'оск ', 'оск.', 'родных', 'родни', 'oskor', 'osk ', 'haqorat', 'hakorat', 'so‘k', 'sokdi'],
 'complaint.cheat': ['читер', 'читы', 'чит ', 'aimbot', 'wallhack', 'cheat', 'hack', 'хак', 'софт', 'стороннее по', 'сторонних по', 'аимбот', 'валхак', 'читак', 'chiter', 'chit ishlat'],
 'complaint.dm': ['дм ', 'dm ', 'убил без причины', 'без причины убил', 'deathmatch', 'random kill', ' дб ', ' db ', 'дб.', 'db.', 'давил машин', 'сбил машин', 'убил просто так', 'non rp cop', 'nonrp cop', 'dm gz', 'дм гз', 'meni urdi', 'meni oлdirdi'],
 'complaint.scam': ['обман', 'скам', 'мошенн', 'scam', 'fraud', 'golpe', 'кинул на деньги', 'кинул при обмене', 'aldadi', 'firibgar'],
 'complaint.rmt_ads': ['реклама', 'продам аккаунт', 'реал', 'rmt', 'advertis', 'spam ads'],
 'complaint.admin': ['админ', 'модератор', 'admin abuse', 'moderador', 'не согласен с наказанием', 'не согласен с баном', 'неправильно выдал наказание', 'снять наказание', 'снятие наказания', 'обжаловать бан', 'выдал мут без причины', 'выдал варн без причины', 'блатит', 'необоснованный бан', 'необоснованный мут'],
 'complaint.invalid': ['ошибочная жалоба', 'отменить жалобу'],
 'report.payment': ['донат', 'оплат', 'платеж', 'платёж', 'возврат денег', 'payment', 'refund', 'pagamento', 'pix'],
 'report.account': ['аккаунт', 'пароль', 'взлом', 'восстанов', 'account', 'password', 'conta', 'senha'],
 'report.help': ['помогите', 'помощь', 'не работает', 'ошибка', 'help', 'ajuda', 'bug'],
 'report.question': ['вопрос', 'подскажите', 'как сделать', 'question', 'pergunta', 'como faço'],
 'report.complaint': ['жалоба', 'нарушение', 'report player', 'denuncia', 'denúncia'],
 'report.offtopic': ['не по теме', 'оффтоп', 'offtopic'],
}
ALIASES = {'cheat':'complaint.cheat','cheats':'complaint.cheat','читы':'complaint.cheat',
 'insult':'complaint.insult','оскорбление':'complaint.insult','оск':'complaint.insult','оскр':'complaint.insult','оск родни':'complaint.insult','dm':'complaint.dm','дм':'complaint.dm','db':'complaint.dm','дб':'complaint.dm',
 'scam':'complaint.scam','обман':'complaint.scam','admin':'complaint.admin','софт':'complaint.cheat',
 'payment':'report.payment','донат':'report.payment','account':'report.account',
 'help':'report.help','question':'report.question','spam':'complaint.rmt_ads'}
RULE_RE = re.compile(r'(?<!\w)(\d{1,3}(?:\.\d{1,3}){1,3})\s*(ОП|ПП|GZ|ОБ|op|pp)?\b', re.I)
NICK_RE = re.compile(r'(?:ник(?:нейм)?|nickname|nick|игрок|player|jogador)\s*[:=\-]\s*([\w-]{3,32})', re.I)
SERVER_RE = re.compile(r'(?:сервер|server|servidor)\s*[:=\-#]?\s*([\w-]{1,32})', re.I)
URL_RE = re.compile(r'https?://\S+', re.I)
EVIDENCE_RE = re.compile(r'\b(скрин(?:шот)?|видео|запись|доказательств[ао]?|screenshot|video|proof|evidence|print|prova|youtu\.?be)\b', re.I)
SPAM_RE = re.compile(r'(?:https?://\S+\s*){3,}|(.)\1{20,}', re.I | re.S)


def normalize_text(value: str | bytes) -> str:
    if isinstance(value, bytes):
        try: value = value.decode('utf-8')
        except UnicodeDecodeError: value = value.decode('cp1251', errors='replace')
    value = unicodedata.normalize('NFKC', value).replace('\u200b', '').replace('\ufeff', '')
    return re.sub(r'\s+', ' ', value).strip()


def detect_language(text: str) -> str:
    text = normalize_text(text).lower()
    if re.search(r'[а-яё]', text): return 'ru'
    if re.search(r'[әғқңөұүһі]', text): return 'kk'
    words = re.findall(r'[a-záàâãçéêíóôõúü]+', text)
    pt = {'não','voce','você','jogador','denuncia','denúncia','obrigado','minha','conta','ajuda','prova','servidor','olá','com','para','que','por','foi','está'}
    kk = {'salam','salem','qalai','qalay','men','magan','maghan','aksha','akkaunt','zhok','zhoq','komek','rahmet','zhaz','oiyn','oyin','nege'}
    en = {'the','and','player','please','help','account','report','with','this','was','banned','cheater'}
    scores = [sum(w in vocab for w in words) for vocab in (pt, kk, en)]
    if re.search(r'[ãõç]', text) or scores[0] > max(scores[1:]): return 'pt'
    if scores[1] > max(scores[0], scores[2]): return 'kk'
    return 'en' if words else 'unknown'


def normalize_violation(raw: str | None, kind: str = 'complaint') -> str | None:
    if not raw: return None
    value = normalize_text(raw).lower()
    if value in KEYWORDS and value.startswith(kind + '.'): return value
    mapped = ALIASES.get(value)
    if mapped and mapped.startswith(kind + '.'): return mapped
    matches = [(sum(term in value for term in terms), cat) for cat, terms in KEYWORDS.items() if cat.startswith(kind + '.')]
    score, cat = max(matches, default=(0, None))
    return cat if score else None


def ticket_text(req: TriageRequest) -> str:
    return normalize_text(' '.join(m.text for m in req.messages if m.role.lower() != 'admin'))


def weak_label(text: str, kind: str, violation: str | None = None) -> tuple[str, float]:
    direct = normalize_violation(violation, kind)
    if direct: return direct, 0.95
    s = ' ' + normalize_text(text).lower() + ' '
    candidates = []
    for cat, terms in KEYWORDS.items():
        if not cat.startswith(kind + '.'): continue
        hits = sum(1 for term in terms if term in s)
        if hits: candidates.append((hits, cat))
    if candidates:
        candidates.sort(reverse=True)
        best = candidates[0]
        ambiguous = len(candidates) > 1 and candidates[1][0] == best[0]
        return best[1], (0.56 if ambiguous else min(0.84, 0.66 + .06 * (best[0] - 1)))
    return ('complaint.other' if kind == 'complaint' else 'report.offtopic'), 0.28


def classify(req: TriageRequest) -> tuple[str, str, float]:
    text = ticket_text(req)
    category, confidence = weak_label(text, req.kind)
    model = load_model() if (category in ('complaint.other', 'report.offtopic') or confidence < 0.6) else None
    if model is not None:
        try:
            probs = model.predict_proba([text])[0]
            index = int(probs.argmax())
            proposed = str(model.classes_[index])
            if proposed.startswith(req.kind + '.') and float(probs[index]) >= 0.45:
                category, confidence = proposed, float(probs[index])
        except (ImportError, OSError, ValueError, AttributeError):
            pass
    lower = text.lower()
    critical = any(w in lower for w in ('взлом', 'угроз', 'угрож', 'hack account', 'stolen account'))
    priority = ('p0' if critical else 'p1' if category in ('report.payment','report.account','complaint.admin','complaint.scam') else 'p2' if category not in ('report.offtopic','complaint.invalid') else 'p3')
    return category, priority, round(confidence, 3)


def extract_facts(req: TriageRequest) -> Extracted:
    text = ticket_text(req)
    nick = NICK_RE.search(text)
    server = SERVER_RE.search(text)
    refs = []
    for m in RULE_RE.finditer(text):
        ref = m.group(1) + (' ' + m.group(2).upper() if m.group(2) else ' ОП')
        if ref not in refs: refs.append(ref)
    return Extracted(nickname=nick.group(1) if nick else None, server=server.group(1) if server else None,
        rule_refs=refs, has_evidence=any(m.attachments > 0 for m in req.messages) or bool(EVIDENCE_RE.search(text) or URL_RE.search(text)))


def is_spam_or_duplicate(req: TriageRequest) -> bool:
    texts = [normalize_text(m.text).lower() for m in req.messages if m.role.lower() != 'admin' and m.text.strip()]
    if any(SPAM_RE.search(t) for t in texts): return True
    if len(texts) > 1 and len(set(texts)) < len(texts): return True
    return False


def deduplicate_records(records: list[dict]) -> list[dict]:
    seen = set(); output = []
    for record in records:
        text = normalize_text(str(record.get('text', ''))).lower()
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen: continue
        seen.add(digest); output.append(record)
    return output
