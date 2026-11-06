"""Золотой набор: ручная разметка 100-150 тикетов для честных метрик классификации.

  python -m evaluation.make_gold sample --n 120 --out ~/gold_to_label.csv   # CSV вне репозитория!
  (откройте в таблице, заполните колонки category и priority по taxonomy.json)
  python -m evaluation.make_gold convert ~/gold_to_label.csv gold.jsonl
  python -m evaluation.run_eval --gold gold.jsonl

Выборка стратифицирована: больше kk/uz/en и репортов, чем в среднем по valid.
В CSV лежат тексты тикетов: не коммитить и не публиковать.
"""
from __future__ import annotations

import argparse
import csv
import json
import random

from .common import load_valid, player_text

QUOTA = {"kk": 0.15, "uz": 0.2, "en": 0.05, "lat": 0.1}  # остальное ru/прочее


def sample(n: int, seed: int = 7) -> list[dict]:
    rnd = random.Random(seed)
    tickets = load_valid()
    by = {}
    for t in tickets:
        by.setdefault(t["lang"], []).append(t)
    out, used = [], set()
    for lang, share in QUOTA.items():
        pool = by.get(lang, [])
        for t in rnd.sample(pool, min(len(pool), round(n * share))):
            out.append(t); used.add(t["ticket_id"])
    rest = [t for t in tickets if t["ticket_id"] not in used]
    reports = [t for t in rest if t["kind"] == "report"]
    out += rnd.sample(reports, min(len(reports), n // 4))
    used |= {t["ticket_id"] for t in out}
    rest = [t for t in rest if t["ticket_id"] not in used]
    out += rnd.sample(rest, max(0, n - len(out)))
    return out[:n]


def main() -> None:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample"); s.add_argument("--n", type=int, default=120); s.add_argument("--out", required=True)
    c = sub.add_parser("convert"); c.add_argument("csv"); c.add_argument("out")
    a = ap.parse_args()
    if a.cmd == "sample":
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["ticket_id", "kind", "lang", "images", "text", "category", "priority"])
            for t in sample(a.n):
                w.writerow([t["ticket_id"], t["kind"], t["lang"], t.get("images_count", 0), player_text(t), "", ""])
        print("записано:", a.out)
    else:
        n = 0
        with open(a.csv, encoding="utf-8", newline="") as f, open(a.out, "w", encoding="utf-8") as o:
            for r in csv.DictReader(f):
                if r["category"].strip() and r["priority"].strip():
                    o.write(json.dumps({"ticket_id": r["ticket_id"], "category": r["category"].strip(),
                                        "priority": r["priority"].strip()}, ensure_ascii=False) + "\n"); n += 1
        print("размеченных тикетов:", n)


if __name__ == "__main__":
    main()
