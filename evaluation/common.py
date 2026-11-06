"""Общий код харнесса: .env, данные, вызов /triage. Только стандартная библиотека.

Данные читаются из DATA_DIR (.env) и в репозиторий не копируются.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_env(path: str | Path = ".env") -> None:
    """Минимальный разбор .env (KEY=VALUE), уже заданные переменные не трогаем."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def data_dir() -> Path:
    load_env()
    d = os.environ.get("DATA_DIR")
    if not d:
        raise SystemExit("DATA_DIR не задан: добавьте его в .env (путь к папке с данными)")
    return Path(d)


def read_jsonl(path: str | Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_valid(path: str | Path | None = None, n: int | None = None) -> list[dict]:
    path = Path(path) if path else data_dir() / "tickets_valid.jsonl"
    out = []
    for t in read_jsonl(path):
        out.append(t)
        if n and len(out) >= n:
            break
    return out


def admin_reply(ticket: dict) -> str:
    """Последний ответ админа. Только для судьи/отчёта, НИКОГДА не уходит в сервис."""
    for m in reversed(ticket.get("messages", [])):
        if m.get("role") == "admin":
            return m.get("text", "")
    return ""


def player_text(ticket: dict) -> str:
    return "\n".join(m["text"] for m in ticket.get("messages", []) if m.get("role") == "player")


def build_request(ticket: dict) -> dict:
    """Запрос к /triage. Сообщения админа вырезаем: иначе утечка ответа (метрики станут фальшивыми)."""
    msgs, first = [], True
    for m in ticket.get("messages", []):
        if m.get("role") == "admin":
            continue
        item = {"role": m["role"], "text": m.get("text", "")}
        if m["role"] == "player" and first:
            item["attachments"] = ticket.get("images_count", 0) or 0
            first = False
        msgs.append(item)
    return {"kind": ticket["kind"], "messages": msgs}


def post_triage(url: str, payload: dict, timeout: float = 30.0) -> dict:
    """POST /triage. Возвращает {ok, status, body, latency, headers, error}."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
            return {"ok": True, "status": r.status, "body": body,
                    "latency": time.perf_counter() - t0, "headers": dict(r.headers), "error": None}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "body": None,
                "latency": time.perf_counter() - t0, "headers": {}, "error": f"HTTP {e.code}"}
    except Exception as e:  # таймаут, обрыв, невалидный JSON
        return {"ok": False, "status": None, "body": None,
                "latency": time.perf_counter() - t0, "headers": {}, "error": type(e).__name__}


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * q
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)
