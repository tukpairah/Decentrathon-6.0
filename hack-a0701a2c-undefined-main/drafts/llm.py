"""Тонкий клиент LLM на Gemini (google-genai): structured output через response_json_schema.

Ключ берётся из окружения через config.api_key() (GEMINI_API_KEY, запасной LLM_API_KEY), в коде его нет. В тестах подставляется fake через параметр llm.
Интерфейс: call_llm(system, user, schema) -> (dict по schema, usage{in,out,usd}); при ошибке бросает исключение.
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from . import config

try:  # drafts работает и без app: тогда стоимость просто не попадает в заголовки ответа
    from app import usage as _usage
except ImportError:  # pragma: no cover
    _usage = None

RETRY_STATUSES = {"RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED"}
RETRY_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 0.5
RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s")
HTTP_TIMEOUT_MS = 10_000  # минимум, который принимает Gemini; держит зависшие запросы от вечной жизни

_client = None
_sleep = time.sleep
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini")
_late_lock = threading.Lock()
LATE_USAGE = {"calls": 0, "in": 0, "out": 0, "usd": 0.0}  # вызовы, которые завершились после нашего таймаута


class RateLimiter:
    """Равномерные слоты: не чаще rpm вызовов в минуту. acquire(max_wait) ждёт слот или возвращает False."""

    def __init__(self, rpm, clock=time.monotonic, sleep=time.sleep):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self._next = 0.0
        self._lock = threading.Lock()
        self._clock, self._sleep = clock, sleep

    def acquire(self, max_wait=None):
        with self._lock:
            now = self._clock()
            slot = max(now, self._next)
            if max_wait is not None and slot - now > max_wait:
                return False
            self._next = slot + self.interval
        if slot > now:
            self._sleep(slot - now)
        return True


_limiter = RateLimiter(config.RPM)
_batch_mode = False


def set_batch_mode(enabled=True):
    """Пакетный режим (make predict): слот ждём без ограничения, таймаут вызова считается от получения слота."""
    global _batch_mode
    _batch_mode = enabled


def _add_late(future):
    if future.cancelled() or future.exception() is not None:
        return
    usage = future.result()[1]
    with _late_lock:
        LATE_USAGE["calls"] += 1
        for key in ("in", "out", "usd"):
            LATE_USAGE[key] += usage[key]


def _get_client():
    global _client
    if _client is None:
        from google import genai
        key = config.api_key()
        if not key:
            raise RuntimeError("не задан GEMINI_API_KEY (или LLM_API_KEY)")
        _client = genai.Client(api_key=key)
    return _client


def _is_retryable(err):
    return getattr(err, "code", None) in RETRY_CODES or getattr(err, "status", None) in RETRY_STATUSES


def _retry_delay(err, attempt):
    m = RETRY_DELAY_RE.search(str(getattr(err, "details", "") or err))
    return float(m.group(1)) if m else BACKOFF_BASE_S * 2 ** (attempt - 1)


def _generation_config(system, schema):
    from google.genai import types
    extra = {}
    if config.THINKING_BUDGET > 0:  # 0 = не передавать: gemini-3.1-flash-lite не думает по умолчанию и отвергает budget=0
        extra["thinking_config"] = types.ThinkingConfig(thinking_budget=config.THINKING_BUDGET)
    return types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=config.MAX_OUT_TOKENS,
        response_mime_type="application/json",
        response_json_schema=schema,
        http_options=types.HttpOptions(timeout=HTTP_TIMEOUT_MS),
        **extra,
    )


def _usage_of(resp):
    meta = getattr(resp, "usage_metadata", None)
    tokens_in = int(getattr(meta, "prompt_token_count", 0) or 0)
    tokens_out = int(getattr(meta, "candidates_token_count", 0) or 0) + int(getattr(meta, "thoughts_token_count", 0) or 0)
    usd = (tokens_in * config.PRICE_IN_PER_M + tokens_out * config.PRICE_OUT_PER_M) / 1e6
    return {"in": tokens_in, "out": tokens_out, "usd": usd}


def _request(client, system, user, schema):
    resp = client.models.generate_content(model=config.MODEL, contents=user, config=_generation_config(system, schema))
    return resp, _usage_of(resp)


def call_llm(system, user, schema):
    """Возвращает (dict по schema, usage{in,out,usd}). Бросает исключение при ошибке/таймауте."""
    deadline = time.monotonic() + config.TIMEOUT_S
    client = _get_client()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if _batch_mode:
            _limiter.acquire()
            deadline = max(deadline, time.monotonic() + config.TIMEOUT_S) if attempt == 1 else deadline
        elif not _limiter.acquire(max_wait=deadline - time.monotonic()):
            raise TimeoutError(f"нет свободного слота DRAFT_RPM={config.RPM} в пределах {config.TIMEOUT_S} с")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"LLM не ответила за {config.TIMEOUT_S} с")
        future = _executor.submit(_request, client, system, user, schema)
        try:
            resp, usage = future.result(timeout=remaining)
        except FutureTimeout:
            future.add_done_callback(_add_late)
            raise TimeoutError(f"LLM не ответила за {config.TIMEOUT_S} с")
        except Exception as err:
            pause = _retry_delay(err, attempt)
            if attempt == MAX_ATTEMPTS or not _is_retryable(err) or time.monotonic() + pause >= deadline:
                raise
            _sleep(pause)
            continue
        if _usage is not None:
            _usage.record(usage["in"], usage["out"], usage["usd"])
        text = getattr(resp, "text", None)
        if not text:  # пустой ответ (блокировка безопасности, обрыв): usage уже записан, ответ не разбираем
            raise ValueError("LLM вернула пустой ответ")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            raise ValueError(f"LLM вернула не JSON: {err}") from err
        return data, usage
    raise RuntimeError("LLM: попытки исчерпаны")  # pragma: no cover