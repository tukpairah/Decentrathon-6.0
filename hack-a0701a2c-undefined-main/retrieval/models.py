from dataclasses import dataclass
from typing import NamedTuple, Optional


@dataclass(frozen=True)
class Rule:
    cite_id: str
    section: str
    ref: str
    text: str


class Citation(NamedTuple):
    ref: str
    code: Optional[str]

    @property
    def label(self) -> str:
        return make_cite_id(self.ref, self.code) if self.code else self.ref


def make_cite_id(ref: str, code: str) -> str:
    return f"{ref} {code}"


def ref_of(cite_id: str) -> str:
    return cite_id.split(" ", 1)[0]
