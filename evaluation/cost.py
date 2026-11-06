"""Стоимость и задержка. Цели кейса: <= $0.002 за тикет, p95 <= 5 с.

  python -m evaluation.cost --pred results/<run>/pred.jsonl

Две цены на тикет:
  cost_usd            фактическая: заголовок X-Cost-Usd от сервиса (на бесплатном тарифе Gemini 0);
  cost_paid_estimate  расчётная: токены X-Tokens-In/Out * DRAFT_PRICE_IN_PER_M / DRAFT_PRICE_OUT_PER_M из .env
                      (старые имена PRICE_IN_PER_M / PRICE_OUT_PER_M тоже понимаются)
                      ($ за 1 млн токенов по платному прайсу выбранной модели).
Цены берите с официальной страницы провайдера, не по памяти.
Для честной задержки запускайте прогон с --workers 1 (иначе в неё попадает очередь).
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

from .common import load_env, percentile, read_jsonl

COST_LIMIT, P95_LIMIT = 0.002, 5.0


def env_price(kind: str) -> float | None:
    """Цена генератора, $ за 1 млн токенов: DRAFT_PRICE_<kind>_PER_M, иначе PRICE_<kind>_PER_M."""
    v = os.environ.get(f"DRAFT_PRICE_{kind}_PER_M") or os.environ.get(f"PRICE_{kind}_PER_M")
    return float(v) if v else None


def ticket_cost(p: dict, pin: float | None, pout: float | None):
    """Фактическая цена из заголовка; если его нет, расчётная по токенам."""
    if p.get("_cost_usd") is not None:
        return p["_cost_usd"]
    return paid_estimate(p, pin, pout)


def paid_estimate(p: dict, pin: float | None, pout: float | None):
    if p.get("_tok_in") is not None and pin is not None and pout is not None:
        return (p["_tok_in"] * pin + (p.get("_tok_out") or 0) * pout) / 1e6
    return None


def stats(xs: list[float]) -> dict:
    return {"n": len(xs), "mean": round(sum(xs) / len(xs), 5), "p50": round(percentile(xs, .5), 5),
            "p95": round(percentile(xs, .95), 5), "max": round(max(xs), 5)} if xs else {"n": 0}


def analyze(preds: list[dict]) -> dict:
    load_env()
    pin, pout = env_price("IN"), env_price("OUT")
    ok = [p for p in preds if p.get("_error") is None]
    costs = [(p, ticket_cost(p, pin, pout)) for p in ok]
    cv = [c for _, c in costs if c is not None]
    lat = [p["_latency"] for p in ok]
    r: dict = {"tickets_ok": len(ok), "tickets_failed": len(preds) - len(ok)}
    r["latency_s"] = {**stats(lat), "p99": round(percentile(lat, .99), 3),
                      "share_over_5s": round(sum(x > P95_LIMIT for x in lat) / len(lat), 4) if lat else None}
    if cv:
        r["cost_usd"] = stats(cv)
        r["cost_usd"]["share_over_limit"] = round(sum(c > COST_LIMIT for c in cv) / len(cv), 4)
    else:
        r["cost_usd"] = "нет данных: сервис не отдаёт X-Cost-Usd / X-Tokens-*, цены не заданы"
    for key in ("_lang_in", "kind"):  # разрез: kk/uz дороже из-за токенизации
        g_cost, g_lat = defaultdict(list), defaultdict(list)
        for p, c in costs:
            g_lat[p.get(key)].append(p["_latency"])
            if c is not None:
                g_cost[p.get(key)].append(c)
        r["by_" + key.strip("_")] = {str(k): {"latency_p95": round(percentile(v, .95), 3),
                                              "cost_mean": round(sum(g_cost[k]) / len(g_cost[k]), 5) if g_cost[k] else None,
                                              "n": len(v)} for k, v in g_lat.items()}
    est = [c for c in (paid_estimate(p, pin, pout) for p in ok) if c is not None]
    if est:
        r["cost_paid_estimate"] = {**stats(est), "price_in_per_m": pin, "price_out_per_m": pout,
                                   "share_over_limit": round(sum(c > COST_LIMIT for c in est) / len(est), 4),
                                   "per_1000_tickets": round(sum(est) / len(est) * 1000, 4)}
    else:
        r["cost_paid_estimate"] = "нет токенов (X-Tokens-*) или не заданы DRAFT_PRICE_IN_PER_M / DRAFT_PRICE_OUT_PER_M"
    pc = r["cost_paid_estimate"] if isinstance(r["cost_paid_estimate"], dict) else r["cost_usd"]
    r["targets"] = {"cost_ok": (pc["mean"] <= COST_LIMIT) if isinstance(pc, dict) and pc.get("n") else None,
                    "p95_ok": r["latency_s"].get("p95", 99) <= P95_LIMIT if lat else None}
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--pred", required=True)
    rep = analyze(list(read_jsonl(ap.parse_args().pred)))
    print(json.dumps(rep, ensure_ascii=False, indent=2))
