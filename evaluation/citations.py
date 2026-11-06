"""Автопроверка цитат правил в черновиках /triage.

Критерий "нет галлюцинаций" (20%): каждая цитата должна
  1) существовать в rules.json (иначе тикет получает 0),
  2) быть релевантной тикету.

Запуск:
  python -m evaluation.citations --pred pred.jsonl [--valid tickets_valid.jsonl] [--out report.json]

Данные берутся из DATA_DIR (.env), в репозиторий не копируются.
В отчёт попадают только ticket_id и цитаты, текст тикетов не пишется.

Формат цитаты: "<ref> <раздел>", например "2.1 ОП", "1.2 GZ", "1.2.7 ЖБ".
Номера пунктов повторяются между разделами, поэтому голый "2.1" двусмысленен:
он считается существующим (ref есть в каком-то разделе), но попадает в
счётчик `ambiguous_bare`. С флагом --strict такая цитата считается ошибкой.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

# Коды разделов. ПОДТВЕРЖДЕНЫ данными (train, поле violation) только ОП, ЖБ, GZ и ПГО (раздел 34).
# Остальные у Тамера (drafts/rules.py) и Рахата (retrieval/sections.py) разные и подобраны по
# названиям разделов. Номера пунктов с кодами FW и ФВ в train относятся к разделу 36, а не к 41/42.
# Пока организаторы не ответили, проверка принимает ЛЮБОЙ из спорных кодов раздела и считает такие
# цитаты отдельно (unconfirmed_code), а не как выдуманные.
CODES_FOR = {30: ["ОП"], 31: ["ЖБ"], 32: ["GZ"], 33: ["ЛД"], 34: ["ПГО", "ГО"],
             35: ["ГВ"], 36: ["СМ", "FW", "ФВ"], 40: ["ОПГ"], 41: ["ВБ", "FW"], 42: ["БФ", "ФВ"]}
CONFIRMED_CODES = {"ОП", "ЖБ", "GZ", "ПГО"}

# Варианты написания -> канонический код (кириллица/латиница, регистр).
CODE_ALIASES = {c.upper(): c for codes in CODES_FOR.values() for c in codes}
CODE_ALIASES.update({"OP": "ОП", "ОР": "ОП", "OП": "ОП", "JB": "ЖБ", "ZHB": "ЖБ", "ZB": "ЖБ",
                     "ГЗ": "GZ", "ЗЗ": "GZ", "LD": "ЛД", "GO": "ГО", "GV": "ГВ", "SM": "СМ",
                     "OPG": "ОПГ", "VB": "ВБ", "BF": "БФ"})

REF_RE = re.compile(r"\d+(?:\.\d+)*")
CODE_RE = re.compile(r"[A-Za-zА-Яа-я]{2,4}")


def load_rules(rules_path: Path) -> dict:
    """Индекс: cite_id (под каждым допустимым кодом раздела) -> текст; ref -> коды; все коды."""
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    cites: dict[str, str] = {}
    by_ref: dict[str, list[str]] = defaultdict(list)
    sections: set[str] = set()
    for sec in data["rules"]:
        for code in CODES_FOR.get(sec["id"], [f"S{sec['id']}"]):
            sections.add(code)
            for p in sec.get("points", []):
                cites[f"{p['ref']} {code}"] = p["text"]
                by_ref[p["ref"]].append(code)
    return {"cites": cites, "by_ref": dict(by_ref), "sections": sections}


def parse_cite(raw: str) -> tuple[str | None, str | None]:
    """'нарушение 2.1 оп' / 'ЖБ 1.1.2' / '2.1' / 'GZ' -> (ref|None, code|None)."""
    s = (raw or "").strip()
    # номер пункта обычно с точкой (2.1, 1.2.7); голое число ("на 60 минут")
    # берём, только если точечных номеров нет
    dotted = re.search(r"\d+(?:\.\d+)+", s)
    m = dotted or REF_RE.search(s)
    ref = m.group(0) if m else None
    code = None
    for w in CODE_RE.findall(s):
        c = CODE_ALIASES.get(w.upper())
        if c:
            code = c
            break
    return ref, code


def check_existence(raw: str, rules: dict, strict: bool = False) -> dict:
    ref, code = parse_cite(raw)
    res = {"raw": raw, "ref": ref, "code": code, "exists": False,
           "ambiguous_bare": False, "canonical": None,
           "unconfirmed_code": bool(code and code not in CONFIRMED_CODES)}
    if ref is None:
        # "GZ" без номера: допустимо только как ссылка на раздел целиком
        if code and code in rules["sections"]:
            res.update(exists=True, canonical=code)
        return res
    if code:
        cid = f"{ref} {code}"
        if cid in rules["cites"]:
            res.update(exists=True, canonical=cid)
        return res
    # голый номер без раздела
    secs = rules["by_ref"].get(ref, [])
    if secs:
        res["ambiguous_bare"] = True  # без раздела цитата всегда неоднозначна
        res["exists"] = not strict
        res["canonical"] = ref
    return res


def taxonomy_refs(tax_path: Path | None) -> dict[str, set[str]]:
    """category -> набор канонических ref/кодов из taxonomy.json."""
    if not tax_path or not tax_path.exists():
        return {}
    tax = json.loads(tax_path.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for c in tax["categories"]:
        s = set()
        for r in c.get("rules", []):
            ref, code = parse_cite(r)
            s.add(f"{ref} {code}" if ref and code else (ref or code))
        out[c["code"]] = {x for x in s if x}
    return out


def check_relevance(cite: dict, pred: dict, tax: dict, admin_ref: str | None) -> str:
    """Дешёвая проверка без LLM. Возвращает основание релевантности.

    taxonomy_match : пункт входит в правила предсказанной категории
    admin_match    : пункт совпал с нарушением из ответа админа (только valid)
    player_ref     : игрок сам назвал этот номер (слабое основание: игроки ошибаются)
    unchecked      : нужна проверка судьёй/человеком
    """
    canon, ref, code = cite["canonical"], cite["ref"], cite["code"]
    cat_rules = tax.get(pred.get("category"), set())
    if canon in cat_rules or (code and code in cat_rules) or (ref in cat_rules):
        return "taxonomy_match"
    if admin_ref and admin_ref in (canon, ref):
        return "admin_match"
    player = {parse_cite(r)[0] for r in pred.get("extracted", {}).get("rule_refs", [])}
    if ref and ref in player:
        return "player_ref"
    return "unchecked"


def admin_ref_of(ticket: dict) -> str | None:
    ref, code = parse_cite(ticket.get("violation") or "")
    return f"{ref} {code}" if ref and code else ref


def run(pred_path: Path, rules_path: Path, tax_path: Path | None,
        valid_path: Path | None, strict: bool) -> dict:
    rules = load_rules(rules_path)
    tax = taxonomy_refs(tax_path)
    admin = {}
    if valid_path and valid_path.exists():
        for line in valid_path.open(encoding="utf-8"):
            t = json.loads(line)
            admin[t["ticket_id"]] = admin_ref_of(t)

    n = with_cites = n_cites = 0
    fabricated, ambiguous, unconfirmed = [], 0, 0
    relevance = Counter()
    zeroed = set()
    for line in pred_path.open(encoding="utf-8"):
        p = json.loads(line)
        n += 1
        cited = (p.get("draft_reply") or {}).get("cited") or []
        if cited:
            with_cites += 1
        for raw in cited:
            n_cites += 1
            c = check_existence(raw, rules, strict)
            if c["ambiguous_bare"]:
                ambiguous += 1
            if c["exists"] and c["unconfirmed_code"]:
                unconfirmed += 1
            if not c["exists"]:
                fabricated.append({"ticket_id": p.get("ticket_id"), "cite": raw})
                zeroed.add(p.get("ticket_id"))
                continue
            relevance[check_relevance(c, p, tax, admin.get(p.get("ticket_id")))] += 1

    return {
        "tickets": n,
        "tickets_with_cites": with_cites,
        "share_with_cites": round(with_cites / n, 4) if n else 0,
        "cites_total": n_cites,
        "fabricated_cites": len(fabricated),
        "fabricated_rate": round(len(fabricated) / n_cites, 4) if n_cites else 0,
        "tickets_zeroed": len(zeroed),
        "ambiguous_bare": ambiguous,
        "unconfirmed_code_cites": unconfirmed,
        "relevance": dict(relevance),
        "fabricated_examples": fabricated[:20],
        "strict": strict,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    data = os.environ.get("DATA_DIR", ".")
    ap.add_argument("--pred", required=True, type=Path)
    ap.add_argument("--rules", type=Path, default=Path(data) / "rules.json")
    ap.add_argument("--taxonomy", type=Path, default=Path(data) / "taxonomy.json")
    ap.add_argument("--valid", type=Path, default=Path(data) / "tickets_valid.jsonl")
    ap.add_argument("--strict", action="store_true",
                    help="голый номер без раздела считать ошибкой")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    rep = run(a.pred, a.rules, a.taxonomy, a.valid, a.strict)
    txt = json.dumps(rep, ensure_ascii=False, indent=2)
    print(txt)
    if a.out:
        a.out.write_text(txt, encoding="utf-8")
    # код возврата 1, если есть выдуманные цитаты: удобно для CI и make
    raise SystemExit(1 if rep["fabricated_cites"] else 0)


if __name__ == "__main__":
    main()
