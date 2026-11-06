import gzip
import json
from pathlib import Path
from typing import Iterator

from .config import load_settings

TICKETS_VALID_FILE = "tickets_valid.jsonl"
TICKETS_TRAIN_FILE = "tickets_train.jsonl.gz"
ADMIN_ROLE = "admin"
MAIN_LANGS = ("ru", "kk", "uz")
OTHER_LANGS = "other"


def data_path(file_name: str) -> Path:
    data_dir = load_settings().data_dir
    if data_dir is None:
        raise FileNotFoundError("Не задан DATA_DIR")
    return data_dir / file_name


def read_tickets(path: Path) -> Iterator[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def player_text(ticket: dict) -> str:
    messages = ticket.get("messages") or []
    return " ".join(m.get("text") or "" for m in messages if m.get("role") != ADMIN_ROLE)


def lang_group(ticket: dict) -> str:
    lang = ticket.get("lang")
    return lang if lang in MAIN_LANGS else OTHER_LANGS
