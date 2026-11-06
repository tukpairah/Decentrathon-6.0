"""Заглушка POST /triage по контракту: чтобы отлаживать харнесс, пока нет настоящего сервиса.

  python -m evaluation.stub_server [--port 8000]
Возвращает правдоподобные, но примитивные ответы (по ключевым словам) и заголовки
X-Cost-Usd / X-Tokens-In / X-Tokens-Out, как это должен делать настоящий сервис.
"""
from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RULE = re.compile(r"\d+(?:\.\d+)+")


def triage(req: dict) -> dict:
    text = " ".join(m.get("text", "") for m in req.get("messages", []) if m.get("role") == "player")
    low = text.lower()
    kind = req.get("kind", "report")
    refs = RULE.findall(text)
    if kind == "complaint":
        cat = "complaint.insult" if "оскорб" in low else "complaint.cheat" if "чит" in low else "complaint.other"
    else:
        cat = "report.payment" if "донат" in low else "report.account" if "взлом" in low else \
              "report.offtopic" if len(low) < 12 else "report.help"
    always = cat in {"report.account", "report.payment", "complaint.admin"}
    cited = ["2.1 ОП"] if cat == "complaint.insult" else []
    return {"lang": "ru", "category": cat, "priority": "p0" if always else "p2",
            "is_spam_or_duplicate": False,
            "extracted": {"nickname": None, "rule_refs": refs, "has_evidence": bool(req["messages"][0].get("attachments")),
                          "server": None},
            "draft_reply": {"lang": "ru", "text": "Здравствуйте! Ваше обращение принято.", "cited": cited},
            "needs_human": always or kind == "complaint", "confidence": 0.5, "reasons": ["заглушка"]}


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/triage":
            self.send_error(404); return
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        body = json.dumps(triage(req), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Cost-Usd", "0.0004"); self.send_header("X-Tokens-In", "900"); self.send_header("X-Tokens-Out", "80")
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8000)
    print(f"stub /triage on :{ap.parse_args().port}")
    ThreadingHTTPServer(("0.0.0.0", ap.parse_args().port), H).serve_forever()
