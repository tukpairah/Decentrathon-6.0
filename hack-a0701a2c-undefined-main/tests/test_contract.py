from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PLAYER_TEXT = "Arman_Petrov оскорблял меня в чате, скрины есть, 2.1 ОП"
BODY = {"kind": "complaint", "messages": [
    {"role": "player", "text": PLAYER_TEXT, "attachments": 2}]}


def test_triage_contract():
    r = client.post("/triage", json=BODY)
    assert r.status_code == 200
    d = r.json()
    for k in ["lang", "category", "priority", "is_spam_or_duplicate", "extracted",
              "draft_reply", "needs_human", "confidence", "reasons"]:
        assert k in d
    assert set(d["draft_reply"]) >= {"lang", "text", "cited"}


def test_rejects_empty_messages():
    assert client.post("/triage", json={"kind": "report", "messages": []}).status_code == 422
