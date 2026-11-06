from fastapi.testclient import TestClient

from app import interfaces, usage
from app.main import app
from app.schemas import DraftReply


def test_cost_headers(monkeypatch):
    def fake(req, lang, rules):
        usage.record(900, 80, 0.0005)
        usage.record(100, 10, 0.0001)
        return DraftReply(lang=lang, text="Здравствуйте! Ваше обращение принято.", cited=[])
    monkeypatch.setattr(interfaces, "generate_draft", fake)
    r = TestClient(app).post("/triage", json={"kind": "report", "messages": [{"role": "player", "text": "помогите"}]})
    assert r.status_code == 200
    assert r.headers["X-Tokens-In"] == "1000" and r.headers["X-Tokens-Out"] == "90"
    assert abs(float(r.headers["X-Cost-Usd"]) - 0.0006) < 1e-9
    assert "usage" not in r.json()  # контракт ответа не изменился
