"""Замер качества и стоимости на tickets_valid.jsonl: python -m drafts.bench [N] [--fake]

Нужны DATA_DIR и GEMINI_API_KEY (без --fake). Ничего не пишет на диск, данные в вывод не логирует,
кроме 5 примеров черновиков в консоль для ручного просмотра.
"""
import json
import os
import random
import statistics
import sys

from . import config
from .examples import ExampleIndex
from .generate import generate_draft, norm_lang, player_text
from .rules import load_rules, select_rules


def _fake(system, user, schema):
    ids = schema["properties"]["cited"]["items"].get("enum", [])
    return {"text": "Здравствуйте! Жалоба передана на рассмотрение.", "cited": ids[:1], "needs_human": False,
            "reasons": []}, {"in": 1100, "out": 90, "usd": 0.0015}


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]) if args else 40
    fake = "--fake" in sys.argv
    rules, idx = load_rules(), ExampleIndex.load()
    valid = [json.loads(l) for l in open(os.path.join(config.DATA_DIR, "tickets_valid.jsonl"), encoding="utf-8")]
    random.seed(7)
    sample = random.sample(valid, n)
    res, shown = [], 0
    for tk in sample:
        txt, lang = player_text(tk), norm_lang(tk.get("lang"), tk)
        cat = "complaint.other" if tk["kind"] == "complaint" else "report.offtopic"
        refs = [tk["rule_refs_raw"]] if tk.get("rule_refs_raw") else []
        cand = select_rules(txt, cat, rules, refs)
        r = generate_draft(tk, lang, cand, idx.search(txt, tk["kind"], lang), category=cat, llm=_fake if fake else None)
        res.append(r)
        if shown < 5 and r["source"] == "llm":
            shown += 1
            print(f"\n[{tk['kind']}/{r['lang']}] {txt[:120]!r}\n -> {r['text']}\n    cited={r['cited']} needs_human={r['needs_human']}")
    src = {s: sum(r["source"] == s for r in res) for s in ("llm", "template", "fallback")}
    usd = [r["usage"]["usd"] for r in res]
    lat = [r["latency_s"] for r in res]
    print(f"\nN={n} источники: {src}")
    print(f"стоимость/тикет: среднее ${statistics.mean(usd):.5f}, p95 ${pct(usd, .95):.5f} (цель <= $0.002)")
    print(f"задержка: среднее {statistics.mean(lat):.2f} c, p95 {pct(lat, .95):.2f} c (цель <= 5 c)")
    print(f"needs_human: {sum(r['needs_human'] for r in res)}/{n}; с цитатами: {sum(bool(r['cited']) for r in res)}/{n}")
    by = {}
    for r in res:
        by.setdefault(r["lang"], []).append(r["source"] == "fallback")
    print("fallback по языкам:", {k: f"{sum(v)}/{len(v)}" for k, v in by.items()})


if __name__ == "__main__":
    main()
