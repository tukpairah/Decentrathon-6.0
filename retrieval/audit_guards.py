import argparse
import logging
import sys
from collections import Counter
from typing import Optional, Sequence

from dotenv import load_dotenv

from .guards import needs_human_guard
from .tickets import TICKETS_VALID_FILE, data_path, player_text, read_tickets

logger = logging.getLogger(__name__)

PREVIEW_LENGTH = 100
KINDS = ("complaint", "report")


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m retrieval.audit_guards")
    parser.add_argument("--show", type=int, default=0)
    args = parser.parse_args(argv)
    totals: Counter = Counter()
    fired: Counter = Counter()
    any_fired: Counter = Counter()
    examples: list[str] = []
    for ticket in read_tickets(data_path(TICKETS_VALID_FILE)):
        kind = ticket.get("kind")
        text = player_text(ticket)
        reasons = needs_human_guard("", "", text)
        totals[kind] += 1
        any_fired[kind] += bool(reasons)
        for reason in reasons:
            fired[(kind, reason)] += 1
        if reasons and len(examples) < args.show:
            examples.append(f"{reasons} {text[:PREVIEW_LENGTH]!r}")
    for kind in KINDS:
        total = totals[kind]
        if not total:
            continue
        sys.stdout.write(f"{kind} total={total} any={any_fired[kind]} "
                         f"({any_fired[kind] / total:.3f})\n")
        for (fired_kind, reason), count in sorted(fired.items()):
            if fired_kind == kind:
                sys.stdout.write(f"  {reason}: {count} ({count / total:.3f})\n")
    for line in examples:
        sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
