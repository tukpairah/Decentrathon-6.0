from typing import Literal, Optional

from pydantic import BaseModel, Field

CATEGORIES = [
    "complaint.insult", "complaint.cheat", "complaint.dm", "complaint.scam",
    "complaint.rmt_ads", "complaint.admin", "complaint.other", "complaint.invalid",
    "report.question", "report.help", "report.complaint", "report.account",
    "report.payment", "report.offtopic",
]
PRIORITIES = ["p0", "p1", "p2", "p3"]
# Эти категории всегда уходят человеку (taxonomy.json -> needs_human_always)
ALWAYS_HUMAN = {"report.account", "report.payment", "complaint.admin"}


class Message(BaseModel):
    role: str
    text: str = ""
    attachments: int = 0


class TriageRequest(BaseModel):
    kind: Literal["complaint", "report"]
    messages: list[Message] = Field(min_length=1)


class Extracted(BaseModel):
    nickname: Optional[str] = None
    rule_refs: list[str] = []
    has_evidence: bool = False
    server: Optional[str] = None


class DraftReply(BaseModel):
    lang: str
    text: str
    cited: list[str] = []  # формат "<пункт> <раздел>", например "2.1 ОП"


class TriageResponse(BaseModel):
    lang: str
    category: str
    priority: Literal["p0", "p1", "p2", "p3"]
    is_spam_or_duplicate: bool
    extracted: Extracted
    draft_reply: DraftReply
    needs_human: bool
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = []
