"""Правила: загрузка rules.json, канонические cite_id вида "<ref> <раздел>", отбор кандидатов.

Номера пунктов повторяются между разделами, поэтому цитата всегда "2.1 ОП", "1.2 GZ", "1.1.2 ЖБ".
"""
import json
import os
import re
from functools import lru_cache

from . import config

# id раздела в rules.json -> код в цитате. 30/31/32 подтверждены данными (ОП, ЖБ, GZ);
# остальные подобраны по частоте кодов в поле violation и ТРЕБУЮТ сверки с организаторами.
SECTION_CODES = {30: "ОП", 31: "ЖБ", 32: "GZ", 33: "ЛД", 34: "ПГО", 35: "ГВ",
                 36: "СМ", 40: "ОПГ", 41: "FW", 42: "ФВ"}

_LATIN2CYR = str.maketrans({"O": "О", "P": "П", "o": "о", "p": "п", "X": "Х", "C": "С", "c": "с"})
_ALIASES = {"OP": "ОП", "ОР": "ОП", "OП": "ОП", "ГЗ": "GZ", "ЗЗ": "GZ", "ЖБ": "ЖБ", "JB": "ЖБ", "ФВ": "ФВ"}
MAIN_SECTIONS = {"ОП", "ЖБ", "GZ"}
_REF = r"\d+(?:\.\d+)*"
_CITE_RE = re.compile(rf"(?:(?<!\w)(?P<pre>[A-Za-zА-Яа-я]{{2,4}})\s*(?P<r1>{_REF})|(?P<r2>{_REF})\s*(?P<post>[A-Za-zА-Яа-я]{{2,4}}))(?!\w)")


def canon(s):
    """'ЖБ 1.1.2', '2.1 OP', '2.1оп' -> '1.1.2 ЖБ', '2.1 ОП'. None, если не похоже на цитату."""
    m = _CITE_RE.search((s or "").strip())
    if not m:
        return None
    ref = m.group("r1") or m.group("r2")
    code = (m.group("pre") or m.group("post") or "").upper()
    code = _ALIASES.get(code, code)
    return f"{ref} {code}"


def find_cites(text):
    """Все цитатоподобные фрагменты в тексте (для проверки выдуманных пунктов)."""
    out = []
    for m in _CITE_RE.finditer(text or ""):
        ref = m.group("r1") or m.group("r2")
        code = (m.group("pre") or m.group("post") or "").upper()
        # '5 минут', '14 дней' и т.п. не цитаты: нужен известный код раздела
        code = _ALIASES.get(code, code)
        if code in set(SECTION_CODES.values()):
            out.append(f"{ref} {code}")
    return out


@lru_cache(maxsize=2)
def load_rules(path=None):
    path = path or os.path.join(config.DATA_DIR, "rules.json")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for sec in raw["rules"]:
        code = SECTION_CODES.get(sec["id"])
        if not code:
            continue
        for p in sec.get("points", []):
            text = re.sub(r"\s+", " ", p["text"]).strip()
            out.append({"cite_id": f"{p['ref']} {code}", "ref": p["ref"], "section": code,
                        "section_title": sec["category"], "text": text})
    return out


@lru_cache(maxsize=2)
def load_taxonomy(path=None):
    path = path or os.path.join(config.DATA_DIR, "taxonomy.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _expand_tax_refs(refs, rules):
    """'2.1' -> '2.1 ОП'; 'ЖБ 1.1.2' -> '1.1.2 ЖБ'; голое 'GZ' -> все пункты GZ."""
    ids = set()
    for r in refs:
        r = r.strip()
        if r in set(SECTION_CODES.values()):
            ids |= {x["cite_id"] for x in rules if x["section"] == r}
        elif (c := canon(r)) and c.split()[1]:
            ids.add(c)
        elif re.fullmatch(_REF, r):
            ids.add(f"{r} ОП")
    return ids


def select_rules(text, category, rules, claimed_refs=None, k=None):
    """Кандидаты для whitelist цитат: правила категории + заявленные игроком + лексически близкие.

    Это единственный список, из которого модель может цитировать.
    """
    k = k or config.MAX_RULES
    by_id = {r["cite_id"]: r for r in rules}
    cat_ids, claimed = set(), set()
    try:
        tax = load_taxonomy()
        for c in tax["categories"]:
            if c["code"] == category:
                cat_ids = _expand_tax_refs(c["rules"], rules)
    except Exception:
        pass
    for raw in claimed_refs or []:
        c = canon(raw) if canon(raw) and canon(raw).split()[1] else (f"{raw.strip()} ОП" if re.fullmatch(_REF, raw.strip()) else None)
        if c in by_id:
            claimed.add(c)

    sims = _similarities(text, rules)
    scored = []
    for r, s in zip(rules, sims):
        in_cat, in_claim = r["cite_id"] in cat_ids, r["cite_id"] in claimed
        # лексический «филлер» берём только из основных разделов и только при заметном сходстве,
        # иначе в whitelist попадают случайные пункты ЛД/FW/СМ
        if not (in_cat or in_claim) and (r["section"] not in MAIN_SECTIONS or s < 0.12):
            continue
        scored.append((s + (0.6 if in_cat else 0) + (0.4 if in_claim else 0), r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:k]]


_VEC_CACHE = {}


def _similarities(text, rules):
    from sklearn.feature_extraction.text import TfidfVectorizer
    key = id(rules)
    if key not in _VEC_CACHE:
        v = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=True)
        _VEC_CACHE[key] = (v, v.fit_transform([r["text"] for r in rules]))
    v, m = _VEC_CACHE[key]
    return (m @ v.transform([text or ""]).T).toarray().ravel()


def clip(rule, n=None):
    n = n or config.RULE_CHARS
    t = rule["text"]
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"
