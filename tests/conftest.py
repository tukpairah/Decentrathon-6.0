import json
from pathlib import Path

import pytest

from retrieval.catalog import load_catalog
from retrieval.rules_index import RulesIndex, reset_index

SYNTHETIC_RULES = {
    "lang": "ru",
    "source": "synthetic",
    "rules": [
        {
            "id": 30, "platform": "game", "category": "Общие правила",
            "points": [
                {"ref": "2.1", "text": "Запрещено оскорблять других игроков в чате."},
                {"ref": "2.2", "text": "Запрещено использовать программы для читерства."},
                {"ref": "3.1", "text": "Запрещена реклама серверов и продажа валюты за деньги."},
            ],
        },
        {
            "id": 31, "platform": "game", "category": "Правила жалоб",
            "points": [
                {"ref": "1.1", "text": "Жалоба подаётся в течение семи суток после случая."},
                {"ref": "1.2", "text": "К жалобе нужно прикрепить видеодоказательства."},
            ],
        },
        {
            "id": 32, "platform": "game", "category": "Зелёная зона",
            "points": [
                {"ref": "2.1", "text": "В безопасной области запрещено убивать игроков."},
                {"ref": "1.2", "text": "Границы безопасной области отмечены на карте."},
            ],
        },
        {"id": 43, "platform": "game", "category": "Термины", "points": []},
    ],
}

SYNTHETIC_TAXONOMY = {
    "categories": [
        {"code": "complaint.insult", "rules": ["2.1 ОП"]},
        {"code": "complaint.cheat", "rules": ["2.2"]},
        {"code": "complaint.dm", "rules": ["2.1", "9.9 ОП", "GZ"]},
        {"code": "complaint.invalid", "rules": ["ЖБ 1.1", "ЖБ 7.7"]},
    ],
}


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def synthetic_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = write_json(tmp_path / "rules.json", SYNTHETIC_RULES)
    taxonomy = write_json(tmp_path / "taxonomy.json", SYNTHETIC_TAXONOMY)
    monkeypatch.setenv("RULES_PATH", str(path))
    monkeypatch.setenv("TAXONOMY_PATH", str(taxonomy))
    monkeypatch.setenv("RETRIEVAL_EMBEDDINGS", "off")
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr("app.main.warm_up_classifier", lambda: False)
    monkeypatch.setattr("drafts.llm._client", None)
    reset_index()
    yield path
    reset_index()


@pytest.fixture
def catalog(synthetic_rules: Path) -> dict:
    return load_catalog(synthetic_rules)


@pytest.fixture
def index(catalog: dict, tmp_path: Path) -> RulesIndex:
    return RulesIndex(catalog, False, "unused-model", tmp_path / "cache")
