import argparse
import gzip
import json

from dotenv import load_dotenv

from .pipeline import triage
from .schemas import Message, TriageRequest


def ticket_to_request(t: dict) -> TriageRequest:
    msgs = [
        Message(role=m.get("role", "player"), text=m.get("text") or "")
        for m in t.get("messages", []) if m.get("role") != "admin"
    ]
    if not msgs:
        msgs = [Message(role="player", text="")]
    msgs[0].attachments = int(t.get("images_count") or 0)
    return TriageRequest(kind=t.get("kind", "report"), messages=msgs)


def enable_batch_mode() -> None:
    from data_prep.classifier import ensure_model
    from drafts import llm

    llm.set_batch_mode(True)
    ensure_model()


def main() -> None:
    load_dotenv()
    enable_batch_mode()
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    opener = gzip.open if a.inp.endswith(".gz") else open
    with opener(a.inp, "rt", encoding="utf-8") as f, open(a.out, "w", encoding="utf-8") as o:
        for line in f:
            t = json.loads(line)
            resp = triage(ticket_to_request(t))
            o.write(json.dumps({"ticket_id": t.get("ticket_id"), **resp.model_dump()},
                               ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
