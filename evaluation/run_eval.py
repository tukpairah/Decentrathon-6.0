"""Прогон valid-тикетов через POST /triage и расчёт метрик.

  python -m evaluation.run_eval --url http://localhost:8000/triage [--n 1000] [--workers 8]
  python -m evaluation.run_eval --workers 1 --n 200      # замер задержки без очереди
  python -m evaluation.run_eval --gold gold.jsonl        # + accuracy / macro-F1 по золотому набору

Результаты: results/<время>/pred.jsonl (с текстами, держать вне git) и summary.json
(только агрегаты, их можно показывать). Сообщения админа в сервис НЕ отправляются.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import citations
from .common import (build_request, data_dir, load_env, load_valid, percentile,
                     post_triage, read_jsonl)
from .promises import find_promises

PRIORITIES = {"p0", "p1", "p2", "p3"}
KNOWN_LANGS = {"ru", "kk", "uz", "en"}


def _hdr_float(h: dict, name: str):
    for k, v in h.items():
        if k.lower() == name:
            try:
                return float(v)
            except ValueError:
                return None
    return None


def one(url: str, t: dict, timeout: float) -> dict:
    r = post_triage(url, build_request(t), timeout)
    rec = {"ticket_id": t["ticket_id"], "kind": t["kind"], "_lang_in": t.get("lang"),
           "_latency": round(r["latency"], 4), "_error": r["error"], "_status": r["status"],
           "_cost_usd": _hdr_float(r["headers"], "x-cost-usd"),
           "_tok_in": _hdr_float(r["headers"], "x-tokens-in"),
           "_tok_out": _hdr_float(r["headers"], "x-tokens-out")}
    if r["ok"] and isinstance(r["body"], dict):
        rec.update(r["body"])
    return rec


def select_tickets(path, n, shuffle=False, seed=42):
    """Первые n тикетов (как раньше) или, с shuffle, детерминированная случайная выборка n из всех."""
    if not shuffle:
        return load_valid(path, n)
    tickets = load_valid(path)
    random.Random(seed).shuffle(tickets)
    return tickets[:n] if n else tickets


def contract_errors(p: dict, categories: set[str]) -> list[str]:
    """Нарушения контракта /triage. Пустой список = всё в порядке."""
    e = []
    for k in ("lang", "category", "priority", "is_spam_or_duplicate", "extracted",
              "draft_reply", "needs_human", "confidence", "reasons"):
        if k not in p:
            e.append(f"нет поля {k}")
    if e:
        return e
    if categories and p["category"] not in categories:
        e.append("категория вне taxonomy")
    if p["priority"] not in PRIORITIES:
        e.append("приоритет вне p0-p3")
    d = p["draft_reply"]
    if not isinstance(d, dict) or not {"lang", "text", "cited"} <= set(d):
        e.append("draft_reply без lang/text/cited")
    elif not isinstance(d["cited"], list):
        e.append("cited не список")
    if not isinstance(p["confidence"], (int, float)) or not 0 <= p["confidence"] <= 1:
        e.append("confidence вне [0,1]")
    return e


def macro_f1(y_true: list, y_pred: list) -> float:
    labels = sorted(set(y_true))
    f = []
    for c in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(f) / len(f) if f else 0.0


def summarize(preds: list[dict], tax: dict | None, gold: dict | None) -> dict:
    n = len(preds)
    ok = [p for p in preds if p.get("_error") is None and "category" in p]
    cats = {c["code"] for c in tax["categories"]} if tax else set()
    always = set(tax.get("needs_human_always", [])) if tax else set()
    needs_rules = {c["code"] for c in tax["categories"] if c.get("rules")} if tax else set()

    s: dict = {"tickets": n, "ok": len(ok), "ok_rate": round(len(ok) / n, 4) if n else 0,
               "errors": dict(Counter(p["_error"] for p in preds if p.get("_error")))}
    s["category_dist"] = dict(Counter(p["category"] for p in ok).most_common())
    s["priority_dist"] = dict(sorted(Counter(p["priority"] for p in ok).items()))
    m = len(ok) or 1
    s["needs_human_share"] = round(sum(1 for p in ok if p["needs_human"]) / m, 4)
    s["spam_or_duplicate_share"] = round(sum(1 for p in ok if p["is_spam_or_duplicate"]) / m, 4)
    s["mean_confidence"] = round(sum(p["confidence"] for p in ok) / m, 4)

    bad = Counter()
    for p in ok:
        for err in contract_errors(p, cats):
            bad[err] += 1
    s["contract_violations"] = dict(bad)

    # жёсткие правила кейса
    always_miss = [p["ticket_id"] for p in ok if p["category"] in always and not p["needs_human"]]
    s["always_human_missed"] = len(always_miss)
    promise_hits, promise_no_human = Counter(), 0
    for p in ok:
        text = (p.get("draft_reply") or {}).get("text", "")
        h = find_promises(text)
        for x in h:
            promise_hits[x] += 1
        if h and not p["needs_human"]:
            promise_no_human += 1
    s["promises_in_drafts"] = dict(promise_hits)
    s["promise_without_needs_human"] = promise_no_human  # должно быть 0

    # язык
    comp = [p for p in ok if p.get("_lang_in") in KNOWN_LANGS]
    if comp:
        s["lang_match_response"] = round(sum(p["lang"] == p["_lang_in"] for p in comp) / len(comp), 4)
        s["lang_match_draft"] = round(
            sum((p["draft_reply"] or {}).get("lang") == p["_lang_in"] for p in comp) / len(comp), 4)

    # цитаты: нужны ли они там, где правила обязательны
    if needs_rules:
        in_rules = [p for p in ok if p["category"] in needs_rules and not p["is_spam_or_duplicate"]]
        miss = sum(1 for p in in_rules if not (p["draft_reply"] or {}).get("cited"))
        s["no_cite_where_rules_expected"] = {"tickets": len(in_rules), "without_cites": miss}

    # скорость (при --workers 1 это честная задержка)
    lat = [p["_latency"] for p in preds if p.get("_latency") is not None]
    s["latency_s"] = {"mean": round(sum(lat) / len(lat), 3) if lat else 0,
                      "p50": round(percentile(lat, .5), 3), "p95": round(percentile(lat, .95), 3)}

    if gold:
        pairs = [(gold[p["ticket_id"]], p) for p in ok if p["ticket_id"] in gold]
        if pairs:
            ct = [g["category"] for g, _ in pairs]; cp = [p["category"] for _, p in pairs]
            pt = [g["priority"] for g, _ in pairs]; pp = [p["priority"] for _, p in pairs]
            s["vs_gold"] = {"n": len(pairs),
                            "category_accuracy": round(sum(a == b for a, b in zip(ct, cp)) / len(pairs), 4),
                            "priority_macro_f1": round(macro_f1(pt, pp), 4)}
    return s


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("TRIAGE_URL", "http://localhost:8000/triage"))
    ap.add_argument("--valid", type=Path)
    ap.add_argument("--n", type=int)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--gold", type=Path, help="jsonl: ticket_id, category, priority (ручная разметка)")
    ap.add_argument("--shuffle", action="store_true", help="случайная выборка вместо первых N (по умолчанию выключено)")
    ap.add_argument("--seed", type=int, default=42, help="seed для --shuffle")
    a = ap.parse_args()

    tickets = select_tickets(a.valid, a.n, a.shuffle, a.seed)
    out = a.out or Path("results") / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        preds = list(ex.map(lambda t: one(a.url, t, a.timeout), tickets))
    wall = time.perf_counter() - t0
    with open(out / "pred.jsonl", "w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    d = data_dir()
    tax = json.loads((d / "taxonomy.json").read_text(encoding="utf-8")) if (d / "taxonomy.json").exists() else None
    gold = {g["ticket_id"]: g for g in read_jsonl(a.gold)} if a.gold else None
    s = summarize(preds, tax, gold)
    s["workers"], s["wall_s"] = a.workers, round(wall, 1)
    if (d / "rules.json").exists():
        c = citations.run(out / "pred.jsonl", d / "rules.json", d / "taxonomy.json",
                          a.valid or d / "tickets_valid.jsonl", strict=False)
        s["citations"] = {k: c[k] for k in ("share_with_cites", "cites_total", "fabricated_cites",
                                             "fabricated_rate", "tickets_zeroed", "ambiguous_bare", "unconfirmed_code_cites", "relevance")}
        s["fabricated_examples"] = c["fabricated_examples"]
    (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(s, ensure_ascii=False, indent=2))
    print(f"\nсохранено: {out}/  (pred.jsonl содержит тексты, не коммитить)")


if __name__ == "__main__":
    main()
