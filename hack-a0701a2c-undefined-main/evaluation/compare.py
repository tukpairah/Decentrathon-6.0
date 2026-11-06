"""Сравнение двух прогонов: что улучшилось, что сломалось.

  python -m evaluation.compare results/A results/B
Печатает разницу метрик summary.json и тикеты, у которых изменились категория,
приоритет или needs_human, а также новые выдуманные цитаты (id и цитаты, без текстов).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import read_jsonl

KEYS = ["ok_rate", "needs_human_share", "spam_or_duplicate_share", "mean_confidence", "always_human_missed",
        "promise_without_needs_human", "lang_match_draft"]
GOOD_UP = {"ok_rate", "lang_match_draft"}


def flat(s: dict) -> dict:
    f = {k: s.get(k) for k in KEYS}
    for k, v in (s.get("citations") or {}).items():
        if isinstance(v, (int, float)):
            f["cit." + k] = v
    f["latency.p95"] = (s.get("latency_s") or {}).get("p95")
    for k, v in (s.get("vs_gold") or {}).items():
        f["gold." + k] = v
    return f


def main(a: Path, b: Path) -> None:
    sa, sb = (json.loads((x / "summary.json").read_text(encoding="utf-8")) for x in (a, b))
    fa, fb = flat(sa), flat(sb)
    print(f"{'метрика':34}{'A':>10}{'B':>10}{'Δ':>10}")
    for k in sorted(set(fa) | set(fb)):
        x, y = fa.get(k), fb.get(k)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            print(f"{k:34}{x:>10}{y:>10}{round(y - x, 4):>+10}")
    pa = {p["ticket_id"]: p for p in read_jsonl(a / "pred.jsonl")}
    pb = {p["ticket_id"]: p for p in read_jsonl(b / "pred.jsonl")}
    ch = {f: [i for i in pa if i in pb and pa[i].get(f) != pb[i].get(f)] for f in ("category", "priority", "needs_human")}
    print("\nизменилось тикетов:", {k: len(v) for k, v in ch.items()})
    ca = {i: set((p.get("draft_reply") or {}).get("cited") or []) for i, p in pa.items()}
    new = [(i, sorted(set((pb[i].get("draft_reply") or {}).get("cited") or []) - ca.get(i, set()))) for i in pb]
    print("новые цитаты в B (первые 10):", [x for x in new if x[1]][:10])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
