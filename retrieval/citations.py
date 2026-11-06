import re
from typing import Iterable, Optional

from .models import Citation, make_cite_id, ref_of
from .sections import CANONICAL_CODES, CODE_ALIASES, PHRASE_CODES

LATIN_TO_CYRILLIC = str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ")
NUMBER = r"\d+(?:\.\d+)*"
DOTTED_NUMBER = r"\d+(?:\.\d+)+"
WORD = r"[^\W\d_]+"
MAX_UNKNOWN_CODE_LENGTH = 3
KEYWORDS = r"(?:пункт\w*|пп|п|тармақ\w*|band\w*|банд\w*)"

CITATION_PATTERN = re.compile(rf"({NUMBER})\.?\s*({WORD})?")
KEYWORD_MENTION = re.compile(
    rf"(?<![^\W\d_]){KEYWORDS}\.?\s*({NUMBER})((?:\s*{WORD}){{0,2}})", re.IGNORECASE
)
CODED_MENTION = re.compile(rf"(?<![\d.])({DOTTED_NUMBER})\s*([A-ZА-ЯЁ]{{2,3}})(?![^\W\d_])")
HINT_SEPARATORS = re.compile(r"[,;/]|\s+и\s+")
PHRASE_PATTERNS = tuple((re.compile(pattern), code) for pattern, code in PHRASE_CODES)


def normalize_code(raw: str) -> Optional[str]:
    code = re.sub(r"[\W_]+", "", raw.upper())
    if code in CANONICAL_CODES:
        return code
    if code in CODE_ALIASES:
        return CODE_ALIASES[code]
    folded = code.translate(LATIN_TO_CYRILLIC)
    return folded if folded in CANONICAL_CODES else None


def parse_citation(raw: str) -> Optional[Citation]:
    if len(re.findall(NUMBER, raw)) != 1:
        return None
    match = CITATION_PATTERN.search(raw)
    if match is None:
        return None
    ref, word = match.group(1), match.group(2)
    if word is None:
        return Citation(ref, None)
    code = normalize_code(word)
    if code is not None:
        return Citation(ref, code)
    if len(word) <= MAX_UNKNOWN_CODE_LENGTH:
        return None
    return Citation(ref, None)


def resolve_citation(raw: str, candidates: Iterable[str]) -> Optional[str]:
    parsed = parse_citation(raw)
    if parsed is None:
        return None
    known = list(dict.fromkeys(candidates))
    if parsed.code is not None:
        cite_id = make_cite_id(parsed.ref, parsed.code)
        return cite_id if cite_id in known else None
    matching = [cite_id for cite_id in known if ref_of(cite_id) == parsed.ref]
    return matching[0] if len(matching) == 1 else None


def split_citations(raw: str) -> list[str]:
    return [piece.strip() for piece in HINT_SEPARATORS.split(raw) if piece.strip()]


def code_from_words(words: str) -> Optional[str]:
    tokens = re.findall(WORD, words)
    if tokens and tokens[0].isupper():
        code = normalize_code(tokens[0])
        if code is not None:
            return code
    phrase = " ".join(tokens).lower().replace("ё", "е")
    for pattern, code in PHRASE_PATTERNS:
        if pattern.search(phrase):
            return code
    return None


def find_mentions(text: str) -> list[Citation]:
    found: list[tuple[int, Citation]] = []
    for match in KEYWORD_MENTION.finditer(text):
        found.append((match.start(), Citation(match.group(1), code_from_words(match.group(2)))))
    for match in CODED_MENTION.finditer(text):
        code = normalize_code(match.group(2))
        if code is not None:
            found.append((match.start(), Citation(match.group(1), code)))
    found.sort(key=lambda item: item[0])
    return list(dict.fromkeys(citation for _, citation in found))
