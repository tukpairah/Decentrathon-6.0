"""Автопроверка запрещённых обещаний в черновиках (ru/kk/uz/en).

Правило кейса: черновик не обещает разбан, возврат средств, наказание другого игрока.
Такие случаи обязаны иметь needs_human=true. Это эвристика по корням слов:
списки kk/uz составлены без носителя, их должен проверить Рахат и узбекоговорящий.
"""
from __future__ import annotations

import re

PATTERNS = {
    "unban": [
        r"разбан", r"разблок", r"сн(?:имем|ят|ять|ят)\s+(?:бан|блокировк|наказани)",
        r"\bunban", r"lift(?:ed)?\s+(?:the\s+)?ban", r"remove(?:d)?\s+(?:the\s+)?ban",
        r"блоктан\s+шығар", r"бұғаттан\s+шығар", r"жазаны\s+алып\s+тастай",
        r"blokdan\s+chiqar", r"блокдан\s+чиқар", r"jazoni\s+olib\s+tashlay",
    ],
    "refund": [
        r"(?:вернём|вернем|вернуть|возместим|компенсируем|компенсаци)\s+.{0,25}(?:деньг|средств|донат|валют|имуществ|машин|дом)",
        r"возврат\s+(?:средств|денег|доната)", r"\brefund", r"reimburs", r"compensat",
        r"(?:ақша|қаражат|донат)\w*\s+.{0,20}қайтар", r"қайтарамыз",
        r"(?:pul|mablag)\w*\s+.{0,20}qaytar", r"qaytaramiz", r"пул\w*\s+.{0,20}қайтар",
    ],
    "punish_other": [
        r"(?:игрок|нарушитель|он)\s+.{0,25}(?:будет\s+наказан|получит\s+(?:мут|бан|наказани|блокировк|деморган|варн))",
        r"(?:накажем|заблокируем|забаним|замутим|накажут)",
        r"will\s+be\s+(?:punished|banned|muted)", r"(?:we|admins?)\s+will\s+(?:ban|mute|punish)",
        r"жазаланады", r"жазалаймыз", r"бұғатталады",
        r"jazolanadi", r"jazolaymiz", r"bloklanadi", r"жазоланади",
    ],
}
_COMPILED = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in PATTERNS.items()}


def find_promises(text: str) -> list[str]:
    """Типы найденных обещаний: unban / refund / punish_other."""
    hits = []
    for kind, pats in _COMPILED.items():
        if any(p.search(text or "") for p in pats):
            hits.append(kind)
    return hits
