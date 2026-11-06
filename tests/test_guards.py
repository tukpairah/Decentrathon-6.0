import pytest

from app.schemas import ALWAYS_HUMAN
from retrieval import guards
from retrieval.guards import needs_human_guard

CLEAN_DRAFT = "Здравствуйте! Мы приняли обращение и проверим информацию."

PAYMENT = {
    "ru": "Я оплатил донат, но деньги списали, а товар не пришёл",
    "kk": "Мен донат төледім, бірақ келмеді",
    "uz": "Men donat uchun to'lov qildim",
    "uz_cyrillic": "Мен донат учун тўлов қилдим",
}
APPEAL = {
    "ru": "Прошу разбан, меня забанили зря",
    "kk": "Бұл баннан кейін апелляция беремін",
    "uz": "Meni noto'g'ri ban qilishdi",
    "uz_cyrillic": "Мени нотўғри бан қилишди",
}
ACCOUNT = {
    "ru": "Мой аккаунт взломали, не могу зайти",
    "kk": "Аккаунтымды бұзып алды",
    "uz": "Akkauntimni buzishdi",
    "uz_cyrillic": "Аккаунтимни бузишди",
}


def flatten(topics: dict) -> list:
    return list(topics.items())


@pytest.mark.parametrize("lang, text", flatten(PAYMENT))
def test_payment_topic(lang, text):
    assert guards.REASON_PAYMENT_TOPIC in needs_human_guard("complaint.other", CLEAN_DRAFT, text)


@pytest.mark.parametrize("lang, text", flatten(APPEAL))
def test_appeal_topic(lang, text):
    assert guards.REASON_APPEAL_TOPIC in needs_human_guard("complaint.other", CLEAN_DRAFT, text)


@pytest.mark.parametrize("lang, text", flatten(ACCOUNT))
def test_account_topic(lang, text):
    assert guards.REASON_ACCOUNT_TOPIC in needs_human_guard("complaint.other", CLEAN_DRAFT, text)


@pytest.mark.parametrize("draft", [
    "Мы сделаем разбан в ближайшее время",
    "Бан будет снят после проверки",
])
def test_unban_promise(draft):
    assert guards.REASON_UNBAN_PROMISE in needs_human_guard("complaint.other", draft)


@pytest.mark.parametrize("draft", [
    "Мы вернём вам деньги",
    "Вам будет выплачена компенсация",
    "Оформим возврат средств",
])
def test_refund_promise(draft):
    assert guards.REASON_REFUND_PROMISE in needs_human_guard("complaint.other", draft)


@pytest.mark.parametrize("draft", [
    "Нарушитель получит мут",
    "Он будет наказан",
    "Мы накажем этого игрока",
])
def test_punishment_promise(draft):
    assert guards.REASON_PUNISHMENT_PROMISE in needs_human_guard("complaint.other", draft)


@pytest.mark.parametrize("text, reason", [
    ("Мой акк сегодня заблокировали", guards.REASON_APPEAL_TOPIC),
    ("Аккаунт забанен навсегда", guards.REASON_APPEAL_TOPIC),
    ("Помогите, взломали", guards.REASON_ACCOUNT_TOPIC),
    ("Профиль был взломан", guards.REASON_ACCOUNT_TOPIC),
    ("Не подходит пароль", guards.REASON_ACCOUNT_TOPIC),
    ("Хочу удалить мой аккаунт", guards.REASON_ACCOUNT_TOPIC),
])
def test_report_forms_found_on_train(text, reason):
    assert reason in needs_human_guard("", "", text)


@pytest.mark.parametrize("text", [
    "Можно ли создать второй аккаунт?",
    "Игрок использует взломанный клиент",
])
def test_neutral_account_mentions_do_not_fire(text):
    assert needs_human_guard("", "", text) == []


def test_yo_and_case_are_ignored():
    assert guards.REASON_PAYMENT_TOPIC in needs_human_guard("x", CLEAN_DRAFT, "ПЛАТЁЖ не прошёл")
    assert guards.REASON_PAYMENT_TOPIC in needs_human_guard("x", CLEAN_DRAFT, "платеж не прошел")
    assert guards.REASON_REFUND_PROMISE in needs_human_guard("x", "ВЕРНЁМ вам деньги")


def test_apostrophe_variants_in_uzbek():
    assert guards.REASON_PAYMENT_TOPIC in needs_human_guard("x", CLEAN_DRAFT, "to‘lov qildim")
    assert guards.REASON_PAYMENT_TOPIC in needs_human_guard("x", CLEAN_DRAFT, "toʻlov qildim")


def test_clean_draft_and_player_text_give_no_reasons():
    player = "Игрок оскорблял меня в чате, есть скриншоты"
    assert needs_human_guard("complaint.insult", CLEAN_DRAFT, player) == []


def test_player_text_defaults_to_empty():
    assert needs_human_guard("complaint.insult", CLEAN_DRAFT) == []


@pytest.mark.parametrize("category", sorted(ALWAYS_HUMAN))
def test_always_human_categories(category):
    assert needs_human_guard(category, CLEAN_DRAFT, "") == [guards.REASON_ALWAYS_HUMAN]


def test_draft_topics_do_not_trigger_player_topics():
    assert needs_human_guard("complaint.insult", "Спасибо за донат", "") == []
