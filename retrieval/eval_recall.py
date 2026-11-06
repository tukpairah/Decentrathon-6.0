import argparse
import logging
import os
import random
import sys
import time
from collections import Counter, defaultdict
from typing import Iterable, Optional, Sequence

import numpy as np
from dotenv import load_dotenv

from .catalog import CatalogError
from .citations import resolve_citation
from .rules_index import RulesIndex, get_index, warm_up_index
from .tickets import TICKETS_TRAIN_FILE, TICKETS_VALID_FILE, data_path, lang_group, read_tickets

logger = logging.getLogger(__name__)

CUTOFFS = (1, 3, 5, 10)
QUERY_ROLES = ("player", "reported_player")
PREVIEW_LENGTH = 100
SOURCE_FILES = {"valid": TICKETS_VALID_FILE, "train": TICKETS_TRAIN_FILE}
DEFAULT_LIMITS = {"valid": 0, "train": 5000}
SAMPLE_SEED = 42
TOP_UNCOVERED = 10
TOTAL_GROUP = "всего"
GROUPS = ("ru", "kk", "uz", "other", TOTAL_GROUP)
WEIGHT_FLAGS = {
    "RRF_WEIGHT_BM25": "w_bm25",
    "RRF_WEIGHT_E5": "w_e5",
    "RRF_WEIGHT_HINTS": "w_hints",
}


def query_text(ticket: dict) -> str:
    messages = ticket.get("messages") or []
    return " ".join(m.get("text") or "" for m in messages if m.get("role") in QUERY_ROLES)


def is_evaluable(ticket: dict) -> bool:
    return ticket.get("kind") == "complaint" and ticket.get("verdict") == "approved"


def target_cite_id(ticket: dict, catalog_ids: list[str]) -> Optional[str]:
    violation = ticket.get("violation")
    return resolve_citation(violation, catalog_ids) if isinstance(violation, str) else None


def ticket_ref_hints(ticket: dict, enabled: bool) -> list[str]:
    raw = ticket.get("rule_refs_raw")
    return [raw] if enabled and isinstance(raw, str) else []


def first_hit_rank(target: str, found: list[str]) -> Optional[int]:
    return found.index(target) + 1 if target in found else None


def format_recall(ranks: list[Optional[int]]) -> str:
    cells = []
    for cutoff in CUTOFFS:
        hits = sum(1 for rank in ranks if rank is not None and rank <= cutoff)
        cells.append(f"@{cutoff}={hits / len(ranks):.3f}")
    return " ".join(cells)


def evaluable_cases(tickets: Iterable[dict], catalog_ids: list[str]) -> list[tuple[dict, str]]:
    cases = []
    for ticket in tickets:
        target = target_cite_id(ticket, catalog_ids) if is_evaluable(ticket) else None
        if target is not None:
            cases.append((ticket, target))
    return cases


def sample_cases(cases: list[tuple[dict, str]], limit: int) -> list[tuple[dict, str]]:
    if limit <= 0 or len(cases) <= limit:
        return cases
    return random.Random(SAMPLE_SEED).sample(cases, limit)


def write_coverage(cases: list[tuple[dict, str]], taxonomy_ids: set[str]) -> None:
    uncovered = Counter(target for _, target in cases if target not in taxonomy_ids)
    covered = len(cases) - sum(uncovered.values())
    sys.stdout.write(f"taxonomy_coverage={covered / len(cases):.3f} ({covered}/{len(cases)})\n")
    for cite_id, count in uncovered.most_common(TOP_UNCOVERED):
        sys.stdout.write(f"  uncovered {cite_id}: {count / len(cases):.3f}\n")


def evaluate(index: RulesIndex, cases: list[tuple[dict, str]], use_hints: bool, show: int) -> None:
    ranks: dict[str, list[Optional[int]]] = defaultdict(list)
    latencies: list[float] = []
    examples: list[str] = []
    for ticket, target in cases:
        query = query_text(ticket)
        hints = ticket_ref_hints(ticket, use_hints)
        begin = time.perf_counter()
        found = [rule.cite_id for rule in index.search(query, max(CUTOFFS), ref_hints=hints)]
        latencies.append((time.perf_counter() - begin) * 1000)
        rank = first_hit_rank(target, found)
        ranks[lang_group(ticket)].append(rank)
        ranks[TOTAL_GROUP].append(rank)
        if len(examples) < show:
            examples.append(f"target={target} rank={rank} query={query[:PREVIEW_LENGTH]!r}")
    for group in GROUPS:
        if ranks[group]:
            sys.stdout.write(f"{group} n={len(ranks[group])} {format_recall(ranks[group])}\n")
    p50, p95 = np.percentile(latencies, [50, 95])
    sys.stdout.write(f"latency_ms p50={p50:.1f} p95={p95:.1f}\n")
    for line in examples:
        sys.stdout.write(line + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m retrieval.eval_recall")
    parser.add_argument("--embeddings", choices=("on", "off"), default=None)
    parser.add_argument("--w-bm25", type=float, default=None)
    parser.add_argument("--w-e5", type=float, default=None)
    parser.add_argument("--w-hints", type=float, default=None)
    parser.add_argument("--ref-hints", choices=("on", "off"), default="off")
    parser.add_argument("--source", choices=tuple(SOURCE_FILES), default="valid")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--show", type=int, default=0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()
    args = build_parser().parse_args(argv)
    if args.embeddings:
        os.environ["RETRIEVAL_EMBEDDINGS"] = args.embeddings
    for name, value in WEIGHT_FLAGS.items():
        if getattr(args, value) is not None:
            os.environ[name] = str(getattr(args, value))
    started = time.perf_counter()
    try:
        index = get_index()
    except CatalogError as error:
        logger.error("%s", error)
        return 1
    build_seconds = time.perf_counter() - started
    warm_up_index()
    limit = DEFAULT_LIMITS[args.source] if args.limit is None else args.limit
    tickets = read_tickets(data_path(SOURCE_FILES[args.source]))
    cases = sample_cases(evaluable_cases(tickets, index.cite_ids), limit)
    if not cases:
        logger.error("Нет тикетов для оценки")
        return 1
    sys.stdout.write(
        f"source={args.source} cases={len(cases)} embeddings_active={index.has_embeddings} "
        f"ref_hints={args.ref_hints} weights={index.weights} "
        f"index_build_seconds={build_seconds:.2f}\n"
    )
    evaluate(index, cases, args.ref_hints == "on", args.show)
    write_coverage(cases, index.taxonomy_ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
