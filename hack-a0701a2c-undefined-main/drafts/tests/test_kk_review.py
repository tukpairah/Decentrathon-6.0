import pytest

from drafts.generate import _FLAG_RE, _PROMISE_RE, build_user_prompt


@pytest.mark.parametrize("text", [
    "Сізді бандан шығарамыз",
    "Жақында разбан жасаймыз",
    "Ақшаңызды қайтарып береміз",
    "Сізге өтемақы береміз",
    "Ақшаңызды қайтарамыз",
])
def test_kk_promises_are_caught(text):
    assert _PROMISE_RE["kk"].search(text)


@pytest.mark.parametrize("text", [
    "Менің аккаунтымды бұзып алды",
    "Аккаунтым бұзылды",
    "Құпия сөзімді ұмытып қалдым",
    "Аккаунтқа кіре алмаймын",
])
def test_kk_account_access_is_caught(text):
    assert _FLAG_RE["account_access"].search(text)


def test_kk_violation_word_is_not_account_access():
    assert not _FLAG_RE["account_access"].search("Ол ережені бұзушылық жасады")


def test_uz_prompt_asks_to_keep_player_alphabet():
    prompt = build_user_prompt({}, "uz", "report", "salom", [], [])
    assert "тем же алфавитом" in prompt
    assert "тем же алфавитом" not in build_user_prompt({}, "kk", "report", "сәлем", [], [])
