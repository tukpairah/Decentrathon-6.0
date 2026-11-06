"""Тесты на синтетических правилах и fake-LLM: данные игры в репозиторий не попадают."""
import pytest

from drafts.generate import generate_draft, norm_lang, is_trivial_report, detect_flags
from drafts.rules import canon, find_cites

RULES = [
    {"cite_id": "2.1 ОП", "ref": "2.1", "section": "ОП", "text": "Запрещено оскорбление игрока. MUTE от 15 до 30 минут."},
    {"cite_id": "1.2 GZ", "ref": "1.2", "section": "GZ", "text": "В зелёной зоне запрещён урон."},
]


def T(kind="complaint", text="оскорбил меня, скрины есть", **kw):
    return {"kind": kind, "messages": [{"role": "player", "text": text}], "images_count": kw.get("images", 1),
            "reported_nick": "Test_Nick"}


def fake(*outs):
    calls = []
    seq = list(outs)

    def f(system, user, schema):
        calls.append((system, user, schema))
        o = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(o, Exception):
            raise o
        return o, {"in": 900, "out": 80, "usd": 0.0013}
    f.calls = calls
    return f


def ok(text="Здравствуйте! Жалоба передана на рассмотрение по п. 2.1 ОП.", cited=("2.1 ОП",), nh=False):
    return {"text": text, "cited": list(cited), "needs_human": nh, "reasons": []}


def test_valid_citation_passes_and_complaint_needs_human():
    r = generate_draft(T(), "ru", RULES, [], llm=fake(ok()))
    assert r["source"] == "llm" and r["cited"] == ["2.1 ОП"] and r["needs_human"] is True


def test_schema_enum_is_whitelist():
    f = fake(ok())
    generate_draft(T(), "ru", RULES, [], llm=f)
    assert f.calls[0][2]["properties"]["cited"]["items"]["enum"] == ["2.1 ОП", "1.2 GZ"]


def test_invented_citation_retries_then_falls_back_without_cites():
    bad = ok(text="Нарушен п. 9.9 ОП.", cited=("9.9 ОП",))
    f = fake(bad)
    r = generate_draft(T(), "ru", RULES, [], llm=f)
    assert r["source"] == "fallback" and r["cited"] == [] and r["needs_human"] and len(f.calls) == 2


def test_invented_citation_in_text_only_is_caught():
    r = generate_draft(T(), "ru", RULES, [], llm=fake(ok(text="См. п. 5.2 ОП.", cited=())))
    assert r["source"] == "fallback"


def test_retry_recovers():
    r = generate_draft(T(), "ru", RULES, [], llm=fake(ok(text="п. 9.9 ОП", cited=("9.9 ОП",)), ok()))
    assert r["source"] == "llm" and r["cited"] == ["2.1 ОП"]


@pytest.mark.parametrize("lang,txt", [("ru", "Игрок получит бан на 7 дней."), ("ru", "Мы вернём ваши деньги."),
                                       ("ru", "Мы разбаним вас."), ("en", "The player will be banned."),
                                       ("uz", "Pulingizni qaytaramiz.")])
def test_promises_rejected(lang, txt):
    r = generate_draft(T(), lang, RULES, [], llm=fake(ok(text=txt, cited=())))
    assert r["source"] == "fallback" and r["needs_human"]


def test_trivial_report_no_llm():
    f = fake(Exception("must not be called"))
    for w in ("помогите", "ау", "Привет!!", "?"):
        r = generate_draft(T("report", w), "ru", [], [], llm=f)
        assert r["source"] == "template" and not r["needs_human"] and r["usage"]["usd"] == 0
    assert not f.calls


def test_payment_and_unban_need_human():
    r = generate_draft(T("report", "оплатил донат, не пришло"), "ru", [], [], llm=fake(ok("Передано.", [])))
    assert r["needs_human"]
    r = generate_draft(T("report", "разбаньте меня пожалуйста"), "ru", [], [], llm=fake(ok("Передано.", [])))
    assert r["needs_human"]


def test_llm_error_falls_back_to_human():
    r = generate_draft(T(), "kk", RULES, [], llm=fake(TimeoutError()))
    assert r["source"] == "fallback" and r["needs_human"] and r["lang"] == "kk"


def test_no_rules_means_empty_cited():
    f = fake(ok("Здравствуйте! Передали вашу просьбу.", []))
    r = generate_draft(T("report", "как устроиться в полицию"), "ru", [], [], llm=f)
    assert r["cited"] == [] and f.calls[0][2]["properties"]["cited"]["maxItems"] == 0


def test_lang_mapping():
    assert norm_lang("kk") == "kk" and norm_lang("pt") == "en" and norm_lang("lat", {"server_lang": "uz"}) == "uz"
    assert norm_lang("und") == "ru"


def test_canon_variants():
    for s in ("2.1 ОП", "2.1 OP", "2.1ОП", "2.1 оп", "нарушение 2.1 ОП"):
        assert canon(s) == "2.1 ОП"
    assert canon("ЖБ 1.1.2") == "1.1.2 ЖБ"
    assert find_cites("14 дней, 5 минут") == []


def test_cp1251_kk_letters_normalized_in_prompt():
    f = fake(ok("Сәлеметсіз бе!", []))
    generate_draft(T("report", "ќазір ґой ѕеге"), "kk", [], [], llm=f)
    assert "қазір" in f.calls[0][1]


def test_prompt_budget():
    long = "а" * 5000
    f = fake(ok("ok", []))
    generate_draft(T(text=long), "ru", RULES * 3, [{"player": "x" * 900, "reply": "y" * 900}] * 5, llm=f)
    assert len(f.calls[0][1]) < 2200
