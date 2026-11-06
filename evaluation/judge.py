"""LLM-судья на Gemini: слепое сравнение черновика с настоящим ответом админа, шкала 1-5.

  python -m evaluation.judge --pred results/<run>/pred.jsonl --n 40 [--dry-run] [--fresh]

.env: GEMINI_API_KEY (ключ с aistudio.google.com), JUDGE_MODEL (Gemini Flash, точное имя модели;
      ДРУГАЯ модель, чем у генератора черновиков на Flash-Lite, иначе судья завышает оценки),
      JUDGE_RPM (запросов в минуту, по умолчанию 5: бесплатный лимит около 5-10 RPM),
      JUDGE_PRICE_IN_PER_M / JUDGE_PRICE_OUT_PER_M (платный прайс МОДЕЛИ СУДЬИ, $ за 1 млн токенов;
      PRICE_* не подставляются: там цена генератора, а судья другая модель),
      JUDGE_THINKING_BUDGET (по умолчанию 0: «размышление» Flash выключено, чтобы не съедало
      лимит ответа и квоту; если модель не разрешает 0, судья сам уберёт эту настройку).

Порядок ответов (черновик/админ) случайный, судья не знает, кто есть кто. Выборка маленькая
(30-50): kk и uz берутся в первую очередь. Результаты пишутся построчно и при повторном запуске
уже оценённые тикеты пропускаются, поэтому обрыв по лимиту не сжигает квоту заново.
При 429 / RESOURCE_EXHAUSTED и 5xx запрос повторяется с паузой (сервер подсказывает её в
retryDelay). Если закончилась ДНЕВНАЯ квота, судья останавливается и сохраняет сделанное.
Результат — оценка LLM-судьи, а не живых админов; так и пишите в отчёте.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from collections import defaultdict
from pathlib import Path

from .common import admin_reply, load_env, load_valid, player_text, read_jsonl

PROMPT = """Ты оцениваешь ответы службы поддержки мобильной ролевой игры. Игрок написал обращение, \
на него есть два ответа, X и Y. Ты не знаешь, кто их написал.

Обращение ({kind}, язык {lang}):
<<<
{player}
>>>

Ответ X:
<<<
{x}
>>>

Ответ Y:
<<<
{y}
>>>

Оцени КАЖДЫЙ ответ от 1 до 5:
5 = как лучший ответ живого админа: по делу, вежливо, коротко, на языке игрока.
3 = терпимо, но есть шаблонность, лишнее или неточность.
1 = не по делу, грубо, на другом языке или содержит выдуманные факты.
Критерии: подходит ли ответ к ситуации; тон админа (вежливо, коротко, по шаблону); нет \
выдуманных пунктов правил и обещаний разбана, возврата средств или наказания другого игрока; \
язык совпадает с языком игрока. Детали, которых ответ не мог знать (точный срок наказания), \
не снижают оценку осторожного ответа.

Ответь ТОЛЬКО JSON: {{"x": <1-5>, "y": <1-5>, "why": "<одно предложение>"}}"""

RETRY_STATUS = {"RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED"}
RETRY_CODES = {429, 500, 502, 503, 504}


class DailyQuotaExceeded(RuntimeError):
    """Дневная квота исчерпана: повторять бессмысленно до завтра."""


def retry_delay_s(err) -> float | None:
    """Пауза, которую подсказал сервер (google.rpc.RetryInfo.retryDelay, например '37s')."""
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(getattr(err, "details", "") or err))
    return float(m.group(1)) if m else None


def is_retryable(err) -> bool:
    return getattr(err, "code", None) in RETRY_CODES or getattr(err, "status", None) in RETRY_STATUS


def is_daily_quota(err) -> bool:
    return bool(re.search(r"per ?day|PerDay|_per_day|RPD", str(getattr(err, "details", "") or err), re.I))


def call_with_retry(fn, *, max_retries: int = 6, base: float = 5.0, cap: float = 120.0,
                    sleep=time.sleep, log=print):
    """Вызывает fn(); при 429/5xx ждёт retryDelay от сервера или экспоненциальную паузу."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:  # google.genai.errors.APIError и сетевые сбои
            if not is_retryable(e):
                raise
            if getattr(e, "code", None) == 429 and is_daily_quota(e):
                raise DailyQuotaExceeded(str(e)[:300]) from e
            if attempt == max_retries:
                raise
            wait = retry_delay_s(e) or min(cap, base * 2 ** attempt)
            wait += random.uniform(0, 1.5)
            log(f"  {getattr(e, 'code', '')} {getattr(e, 'status', '')}: пауза {wait:.0f} с "
                f"(попытка {attempt + 1}/{max_retries})")
            sleep(wait)


class RateLimiter:
    """Не чаще rpm запросов в минуту (равномерно)."""

    def __init__(self, rpm: float, clock=time.monotonic, sleep=time.sleep):
        self.gap, self.clock, self.sleep, self.last = 60.0 / max(rpm, 0.1), clock, sleep, None

    def wait(self) -> None:
        if self.last is not None:
            left = self.gap - (self.clock() - self.last)
            if left > 0:
                self.sleep(left)
        self.last = self.clock()


def pick(preds: list[dict], n: int, seed: int = 11) -> list[dict]:
    rnd = random.Random(seed)
    ok = [p for p in preds if p.get("_error") is None and "draft_reply" in p]
    prio = [p for p in ok if p.get("_lang_in") in ("kk", "uz")][: max(1, n // 3)]  # не больше трети
    rest = [p for p in ok if p not in prio]
    return prio + rnd.sample(rest, min(len(rest), max(0, n - len(prio))))


def parse(text: str):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0))
        x, y = int(d["x"]), int(d["y"])
        return (x, y, str(d.get("why", ""))) if 1 <= x <= 5 and 1 <= y <= 5 else None
    except Exception:
        return None


def make_gemini(model: str):
    """Функция prompt -> (text, tokens_in, tokens_out). Импорт SDK только здесь."""
    from google import genai  # pip install google-genai
    from google.genai import errors, types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    schema = types.Schema(type="OBJECT", required=["x", "y", "why"], properties={
        "x": types.Schema(type="INTEGER"), "y": types.Schema(type="INTEGER"), "why": types.Schema(type="STRING")})

    def config(thinking: bool):
        kw = dict(temperature=0, max_output_tokens=1024, response_mime_type="application/json",
                  response_schema=schema)
        if thinking:
            kw["thinking_config"] = types.ThinkingConfig(
                thinking_budget=int(os.environ.get("JUDGE_THINKING_BUDGET", "0")))
        return types.GenerateContentConfig(**kw)

    state = {"cfg": config(True)}

    def ask(prompt: str):
        try:
            r = client.models.generate_content(model=model, contents=prompt, config=state["cfg"])
        except errors.APIError as e:
            # модель не принимает thinking_budget=0 (например, требует размышление): убираем настройку
            if e.code == 400 and "thinking" in str(e).lower() and "thinking_config" in state["cfg"].model_fields_set:
                print("  модель не принимает thinking_budget, отправляю без него")
                state["cfg"] = config(False)
                r = client.models.generate_content(model=model, contents=prompt, config=state["cfg"])
            else:
                raise
        u = r.usage_metadata
        out = (getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
        return r.text, getattr(u, "prompt_token_count", 0) or 0, out
    return ask


def price(name: str) -> float | None:
    v = os.environ.get(f"JUDGE_{name}")
    return float(v) if v else None


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if "draft" in r]
    g = defaultdict(list)
    for r in ok:
        g["all"].append(r); g[r["lang"]].append(r)
    s = {k: {"n": len(v), "draft_mean": round(sum(r["draft"] for r in v) / len(v), 2),
             "admin_mean": round(sum(r["admin"] for r in v) / len(v), 2),
             "draft_ge4": round(sum(r["draft"] >= 4 for r in v) / len(v), 3),
             "draft_not_worse": round(sum(r["draft"] >= r["admin"] for r in v) / len(v), 3)}
         for k, v in g.items()}
    tin = sum(r.get("tok_in", 0) for r in rows); tout = sum(r.get("tok_out", 0) for r in rows)
    pin, pout = price("PRICE_IN_PER_M"), price("PRICE_OUT_PER_M")
    cost = {"tokens_in": tin, "tokens_out": tout, "actual_usd_free_tier": 0.0}
    if pin is not None and pout is not None and rows:
        est = (tin * pin + tout * pout) / 1e6
        cost.update(paid_estimate_usd=round(est, 6), paid_estimate_per_1000=round(est / len(rows) * 1000, 4),
                    price_in_per_m=pin, price_out_per_m=pout)
    else:
        cost["paid_estimate_usd"] = "задайте JUDGE_PRICE_IN_PER_M / JUDGE_PRICE_OUT_PER_M (прайс модели судьи)"
    return {"judged": len(ok), "parse_errors": len(rows) - len(ok), "scores": s, "cost": cost}


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True); ap.add_argument("--valid"); ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--out", default="results/judge_results.jsonl")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    if a.n > 50:
        print(f"внимание: --n {a.n} на бесплатном тарифе займёт много времени и квоты")
    valid = {t["ticket_id"]: t for t in load_valid(a.valid)}
    sel = pick(list(read_jsonl(a.pred)), a.n)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    if a.fresh and out.exists():
        out.unlink()
    done = {r["ticket_id"] for r in read_jsonl(out)} if out.exists() else set()
    todo = [p for p in sel if p["ticket_id"] not in done]
    model = os.environ.get("JUDGE_MODEL", "")
    gens = {os.environ.get(k) for k in ("LLM_MODEL", "DRAFT_MODEL", "GEMINI_MODEL", "GENERATOR_MODEL")} - {None, ""}
    if model and model in gens:
        print("внимание: судья и генератор черновиков одна модель, оценки могут быть завышены")
    print(f"выборка {len(sel)}, уже оценено {len(sel) - len(todo)}, осталось {len(todo)}")

    rnd = random.Random(5)
    ask = None if a.dry_run else make_gemini(model or "")
    limiter = RateLimiter(float(os.environ.get("JUDGE_RPM", "5")))
    with open(out, "a", encoding="utf-8") as f:
        for i, p in enumerate(todo, 1):
            t = valid[p["ticket_id"]]
            draft, real = p["draft_reply"]["text"], admin_reply(t)
            flip = rnd.random() < 0.5  # True: X = админ, Y = черновик
            x, y = (real, draft) if flip else (draft, real)
            prompt = PROMPT.format(kind=t["kind"], lang=t["lang"], player=player_text(t), x=x, y=y)
            if a.dry_run:
                print(prompt[:700]); return
            limiter.wait()
            try:
                text, tin, tout = call_with_retry(lambda: ask(prompt))
            except DailyQuotaExceeded as e:
                print(f"дневная квота исчерпана, сохранено {i - 1} новых оценок. Запустите завтра или "
                      f"с другим ключом: уже оценённые тикеты пропустятся.\n{e}")
                break
            res = parse(text)
            row = {"ticket_id": p["ticket_id"], "lang": t["lang"], "kind": t["kind"], "tok_in": tin, "tok_out": tout}
            if res:
                sx, sy, why = res
                row.update(draft=sy if flip else sx, admin=sx if flip else sy, why=why)
            else:
                row["error"] = "parse"
            f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
            print(f"  {i}/{len(todo)} {row.get('draft', '?')}/{row.get('admin', '?')}")
    rows = [r for r in read_jsonl(out) if r["ticket_id"] in {p["ticket_id"] for p in sel}]
    summ = summarize(rows)
    print(json.dumps(summ, ensure_ascii=False, indent=2))
    out.with_suffix(".summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
