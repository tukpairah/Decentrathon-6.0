"""Отчёт по казахскому и узбекскому (15% оценки) + файл для носителей.

  python -m evaluation.multilang --pred results/<run>/pred.jsonl [--export-native kk.csv --lang kk --n 30]

Проверяет: символы-двойники cp1251 до/после normalize_text (если есть data_prep.normalize),
буквы ў в узбекском (в узбекской кириллице она настоящая, замена на ұ испортит текст),
язык и алфавит черновиков. Оценку качества текста дают только носители: см. --export-native.
В CSV для носителей лежат тексты тикетов: не коммитить и не публиковать.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict

from .common import load_valid, player_text, read_jsonl

LOOKALIKE = {"ќ": "қ", "ґ": "ғ", "ѕ": "ң", "є": "ә", "ј": "ө", "ў": "ұ", "ї": "ү"}  # из PDF кейса
KK_LETTERS = set("қғңәөұүіһ")
UZ_CYR = set("ўқғҳ")
CYR = lambda s: sum("а" <= c.lower() <= "я" or c.lower() in "ёіңғқәөұүһўҳ" for c in s)
LAT = lambda s: sum("a" <= c.lower() <= "z" for c in s)


def get_normalizer():
    try:
        from data_prep.normalize import normalize_text  # модуль Дани
        return normalize_text, "data_prep.normalize"
    except Exception:
        return None, None


def lookalike_report(tickets: list[dict]) -> dict:
    norm, src = get_normalizer()
    before, after, u_in_uz = Counter(), Counter(), 0
    for t in tickets:
        txt = " ".join(m["text"] for m in t["messages"] if m["role"] != "admin")
        has = [c for c in LOOKALIKE if c in txt]
        for c in has:
            before[(t["lang"], c)] += 1
        if t["lang"] == "uz" and "ў" in txt:
            u_in_uz += 1
        if norm:
            out = norm(txt)
            out = out[0] if isinstance(out, tuple) else out
            for c in LOOKALIKE:
                if c in out:
                    after[(t["lang"], c)] += 1
    fmt = lambda c: {f"{l}:{ch}": n for (l, ch), n in sorted(c.items())}
    return {"normalizer": src or "не найден (data_prep.normalize)", "before": fmt(before),
            "after": fmt(after) if norm else None, "uz_tickets_with_ў": u_in_uz,
            "note": "ў в uz легитимна: нормализатор не должен менять её для uz-текста"}


def draft_report(preds: list[dict], lang: str) -> dict:
    sel = [p for p in preds if p.get("_lang_in") == lang and p.get("_error") is None and "draft_reply" in p]
    if not sel:
        return {"n": 0}
    texts = [p["draft_reply"].get("text", "") for p in sel]
    r = {"n": len(sel),
         "draft_lang_match": round(sum(p["draft_reply"].get("lang") == lang for p in sel) / len(sel), 3),
         "needs_human_share": round(sum(p["needs_human"] for p in sel) / len(sel), 3),
         "lookalike_left_in_drafts": sum(any(c in t for c in LOOKALIKE) for t in texts)}
    if lang == "kk":
        r["with_kazakh_letters"] = round(sum(any(c in KK_LETTERS for c in t.lower()) for t in texts) / len(texts), 3)
    if lang == "uz":
        lat = sum(LAT(t) > CYR(t) for t in texts)
        r["script"] = {"latin": lat, "cyrillic": len(texts) - lat}
    return r


def export_native(preds, valid, lang, n, path):
    by = {t["ticket_id"]: t for t in valid}
    rows = [p for p in preds if p.get("_lang_in") == lang and "draft_reply" in p][:n]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticket_id", "player_text", "draft", "score_1_5", "grammar_ok", "natural_ok", "comment"])
        for p in rows:
            w.writerow([p["ticket_id"], player_text(by[p["ticket_id"]]), p["draft_reply"]["text"], "", "", "", ""])
    print(f"для носителей ({lang}): {len(rows)} строк -> {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True); ap.add_argument("--valid")
    ap.add_argument("--export-native"); ap.add_argument("--lang", default="kk"); ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    valid = load_valid(a.valid)
    preds = list(read_jsonl(a.pred))
    langs = Counter(t["lang"] for t in valid)
    rep = {"valid_langs": dict(langs.most_common()), "cp1251": lookalike_report(valid),
           "drafts": {l: draft_report(preds, l) for l in ("kk", "uz")}}
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if a.export_native:
        export_native(preds, valid, a.lang, a.n, a.export_native)


if __name__ == "__main__":
    main()
