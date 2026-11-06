"""Настройки модуля drafts. Ключи и пути только из окружения / .env, в коде их нет."""
import os

try:  # .env необязателен
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass

DATA_DIR = os.environ.get("DATA_DIR", "")  # вне репозитория: tickets_*.jsonl, rules.json, taxonomy.json
MODEL = os.environ.get("DRAFT_MODEL") or "gemini-3.1-flash-lite"


def _float_env(name, default=0.0):
    value = os.environ.get(name, "").strip()
    return float(value) if value else default


# Цены за 1 млн токенов, USD; пусто -> 0 (бесплатный уровень). Сверить с прайсом перед отчётом.
PRICE_IN_PER_M = _float_env("DRAFT_PRICE_IN_PER_M")
PRICE_OUT_PER_M = _float_env("DRAFT_PRICE_OUT_PER_M")
THINKING_BUDGET = int(os.environ.get("DRAFT_THINKING_BUDGET", "0") or 0)  # 0 = без thinking, ради цены и задержки
MAX_OUT_TOKENS = int(os.environ.get("DRAFT_MAX_OUT", "260"))
RPM = float(os.environ.get("DRAFT_RPM", "12") or 12)  # бесплатный ключ: вызовы ждут слот, а не ловят 429
TIMEOUT_S = float(os.environ.get("DRAFT_TIMEOUT", "5"))  # медленный хвост уходит в fallback; брошенные вызовы считаются в llm.LATE_USAGE

# Бюджет контекста (символы), держит стоимость <= $0.002 за тикет
MAX_RULES = int(os.environ.get("DRAFT_MAX_RULES", "4"))
RULE_CHARS = 300
TICKET_CHARS = 500
MAX_EXAMPLES = 2
EXAMPLE_CHARS = 200

API_KEY_VARS = ("GEMINI_API_KEY", "LLM_API_KEY")  # основной и запасной


def api_key():
    """Ключ LLM из окружения: GEMINI_API_KEY, иначе LLM_API_KEY. Пустая строка, если не задан ни один."""
    for name in API_KEY_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


SUPPORTED_LANGS = ("ru", "kk", "uz", "en")
