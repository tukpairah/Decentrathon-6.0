from types import SimpleNamespace as NS

from drafts.adapter import generate_draft, rule_to_dict, req_to_ticket


class Reply:  # заменяет app.schemas.DraftReply
    def __init__(self, lang, text, cited):
        self.lang, self.text, self.cited = lang, text, cited


def req(kind="complaint", text="оскорбил меня", att=2):
    return NS(kind=kind, messages=[NS(role="player", text=text, attachments=att)])


def llm(system, user, schema):
    return {"text": "Здравствуйте! Жалоба передана на рассмотрение по п. 2.1 ОП.", "cited": ["2.1 ОП"],
            "needs_human": False, "reasons": []}, {"in": 1, "out": 1, "usd": 0}


def test_rule_variants():
    assert rule_to_dict(NS(cite_id="2.1 ОП", text="t"))["cite_id"] == "2.1 ОП"
    assert rule_to_dict(NS(ref="2.1", section="ОП", text="t"))["cite_id"] == "2.1 ОП"
    assert rule_to_dict({"cite_id": "1.2 GZ", "text": "t"})["cite_id"] == "1.2 GZ"


def test_ticket_images():
    assert req_to_ticket(req(att=3))["images_count"] == 3


def test_end_to_end():
    d = generate_draft(req(), "ru", [NS(cite_id="2.1 ОП", text="Запрещено оскорбление")], llm=llm,
                       examples_index=NS(search=lambda *a: []), reply_cls=Reply)
    assert d.cited == ["2.1 ОП"] and d.lang == "ru"


def test_trivial_report_returns_reply_without_llm():
    d = generate_draft(req("report", "ау", 0), "ru", [], llm=None, examples_index=NS(search=lambda *a: []),
                       reply_cls=Reply)
    assert d.cited == [] and d.text
