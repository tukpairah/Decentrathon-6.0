import gzip
import json
import logging
import warnings

import pytest

from app.schemas import Message, TriageRequest
from data_prep import classifier

INSULT = "Игрок оскорбил меня и мою мать матом в чате, скрины прилагаю"
CHEAT = "Игрок использует читы и аимбот, стреляет сквозь стены"


def complaint(text: str) -> TriageRequest:
    return TriageRequest(kind="complaint", messages=[Message(role="player", text=text)])


@pytest.fixture
def synthetic_data_dir(tmp_path, monkeypatch):
    rows = []
    for index in range(30):
        rows.append({"kind": "complaint", "category": "complaint.insult",
                     "messages": [{"role": "player", "text": f"{INSULT} {index}"}]})
        rows.append({"kind": "complaint", "category": "complaint.cheat",
                     "messages": [{"role": "player", "text": f"{CHEAT} {index}"}]})
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with gzip.open(data_dir / classifier.TRAIN_FILE, "wt", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(row, ensure_ascii=False) for row in rows))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    return data_dir


def test_model_lives_in_cache_not_in_package():
    assert classifier.model_path().parent != classifier.ROOT


def test_ensure_model_trains_into_cache(synthetic_data_dir):
    assert not classifier.model_path().exists()
    assert classifier.ensure_model() is True
    assert classifier.model_path().exists()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        model = classifier.load_model()
    assert set(model.classes_) == {"complaint.insult", "complaint.cheat"}
    assert classifier.ensure_model() is True


def test_trained_model_classifies_ambiguous_insult(synthetic_data_dir):
    classifier.ensure_model()
    category, _, _ = classifier.classify(complaint("он оскорбил мать матом"))
    assert category == "complaint.insult"


def test_without_data_dir_rules_only_and_warning(monkeypatch, caplog):
    monkeypatch.delenv("DATA_DIR", raising=False)
    with caplog.at_level(logging.WARNING):
        assert classifier.ensure_model() is False
    assert "только правила" in caplog.text
    category, _, _ = classifier.classify(complaint(INSULT))
    assert category == "complaint.insult"
