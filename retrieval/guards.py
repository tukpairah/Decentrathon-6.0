import re

from app.schemas import ALWAYS_HUMAN

REASON_ALWAYS_HUMAN = "категория всегда идёт человеку"
REASON_PAYMENT_TOPIC = "в обращении тема платежей или доната"
REASON_APPEAL_TOPIC = "в обращении апелляция бана или наказания"
REASON_ACCOUNT_TOPIC = "в обращении взлом или потеря доступа к аккаунту"
REASON_UNBAN_PROMISE = "в черновике обещан разбан"
REASON_REFUND_PROMISE = "в черновике обещан возврат средств или компенсация"
REASON_PUNISHMENT_PROMISE = "в черновике обещано наказание другого игрока"

APOSTROPHES = re.compile("[ʻʼ’‘`]")

PAYMENT_RU = (
    r"донат", r"плат[её]ж", r"оплат", r"списал", r"списан", r"покупк", r"реальн\w+\s+деньг",
    r"верни\w*\s+(?:мне\s+)?(?:деньги|денег|средства)", r"вернуть\s+(?:деньги|денег|средства)",
)
PAYMENT_KK = (r"донат", r"төлем", r"төле[дуй]", r"төлен", r"сатып\s+ал", r"ақша")
PAYMENT_UZ = (
    r"donat", r"to'?lov", r"to'?lad", r"\bpul(?:im|ni|ga|dan|i)?\b", r"sotib\s+ol", r"xarid",
    r"донат", r"т[ўу]лов", r"т[ўу]лад", r"\bпул(?:им|ни|га|дан|и)?\b", r"сотиб\s+ол", r"харид",
)

APPEAL_RU = (
    r"раз\s*бан", r"апелляц", r"сними\w*\s+(?:с\s+меня\s+)?(?:бан|блокиров)", r"снять\s+бан",
    r"обжалов\w*\s+(?:бан|блок|наказан)", r"несправедлив\w*\s+(?:бан|наказан|блок)",
    r"меня\s+(?:забанили|заблокировали)", r"забанил\w*\s+(?:меня|зря|не\s+за)",
    r"(?:выдали|получил\w*)\s+бан", r"бан\s+(?:по\s+ошибке|незаслуженно)",
    r"акк\w*\s+(?:\w+\s+)?(?:заблок|забан)\w*",
)
APPEAL_KK = (
    r"раз\s*бан", r"апелляц", r"бұғат\w*", r"мені\s+бан\w*", r"әділетсіз\s+(?:бан|жаза)",
    r"бан\w*\s+(?:алып|шеш)",
)
APPEAL_UZ = (
    r"razban", r"apellyatsiya", r"meni\s+ban\w*", r"noto'?g'?ri\s+ban", r"bloklan\w*",
    r"ban\w*\s+(?:yech|ol)\w*", r"bandan\s+chiqar",
    r"апелляция", r"мени\s+бан\w*", r"нотўғри\s+бан", r"блоклан\w*", r"бан\w*\s+(?:олинг|ечинг)",
)

ACCOUNT_RU = (
    r"взлом\w*\s+(?:мо\w+\s+)?акк\w*", r"акк\w*\s+(?:был\w*\s+)?(?:взлом|украд|украл|угна)\w*",
    r"меня\s+взломал\w*", r"угнал\w*\s+акк\w*", r"украл\w*\s+(?:мой\s+)?акк\w*",
    r"потерял\w*\s+(?:доступ|аккаунт|акк|пароль)", r"утерян\w*\s+(?:доступ|аккаунт|пароль)",
    r"не\s+могу\s+(?:зайти|войти)", r"нет\s+доступа", r"забыл\w*\s+пароль",
    r"восстанов\w*\s+(?:доступ|акк\w*)", r"взломали\b", r"взломан[аоы]?\b", r"парол\w*",
    r"удал\w*\s+(?:мо\w+\s+)?акк\w*",
)
ACCOUNT_KK = (
    r"акк\w*\s+(?:\w+\s+)?(?:бұз|ұрла|жоғалт)\w*", r"кіре\s+алмай\w*", r"құпия\s*сөз\w*",
)
ACCOUNT_UZ = (
    r"akkaunt\w*\s+(?:\w+\s+)?(?:buz|o'?g'?irla|yo'?qot|hack)\w*", r"kira\s+olm\w*",
    r"parol\w*\s+(?:unut|yo'?qot|almash)\w*",
    r"аккаунт\w*\s+(?:\w+\s+)?(?:буз|ўғирла|йўқот)\w*", r"кира\s+олма\w*",
    r"кир\w*\s+олмаяпман", r"парол\w*\s+(?:унут|йўқот|алмаш)\w*",
)

UNBAN_PROMISE = (
    r"разбан\w*", r"разблокир\w*", r"сними\w*\s+(?:с\s+вас\s+)?(?:бан|блокиров)\w*",
    r"снят\w*\s+(?:бан|блокиров|наказан)\w*", r"отменим\s+(?:бан|наказан)\w*",
    r"бан\s+будет\s+снят", r"наказание\s+будет\s+(?:снято|отменено)",
    r"вернем\s+доступ", r"восстановим\s+(?:доступ|акк\w*)",
    r"бан\w*\s+алып\s+тастаймыз", r"бұғатты\s+алып\s+тастаймыз",
    r"bandan\s+chiqaramiz", r"banni\s+olib\s+tashlaymiz", r"blokdan\s+chiqaramiz",
)
REFUND_PROMISE = (
    r"верн\w+\s+(?:вам\s+)?(?:деньги|денег|средства|донат|платеж\w*)",
    r"возврат\w*\s+(?:средств|денег|платеж\w*|доната)", r"компенсац\w*", r"компенсир\w*",
    r"возместим", r"возмещен\w*", r"начислим\s+(?:вам\s+)?(?:компенсац|вознагражд)\w*",
    r"ақшаңызды\s+қайтарамыз", r"өтемақы", r"pulingizni\s+qaytaramiz", r"kompensatsiya",
    r"пулингизни\s+қайтарамиз",
)
PUNISHMENT_PROMISE = (
    r"получит\w*\s+(?:мут|бан|наказан\w*|предупрежден\w*|блокировк\w*|по\s+заслугам)",
    r"буд(?:ет|ут)\s+(?:наказан|забанен|заблокирован|замучен|оштрафован)\w*",
    r"накажем", r"забаним", r"заблокируем", r"выдадим\s+(?:ему\s+)?(?:мут|бан|наказан\w*)",
    r"понесет\s+наказание", r"(?:мут|бан)\s+(?:будет\s+)?выдан\w*",
    r"жазалан\w*", r"жазаға\s+тартыл\w*", r"бандалады",
    r"jazolan\w*", r"jazolaymiz", r"ban\s+oladi", r"bloklanadi",
    r"жазолан\w*", r"жазолаймиз",
)


def union(*groups: tuple[str, ...]) -> re.Pattern:
    return re.compile("|".join(pattern for group in groups for pattern in group))


PAYMENT_TOPIC = union(PAYMENT_RU, PAYMENT_KK, PAYMENT_UZ)
APPEAL_TOPIC = union(APPEAL_RU, APPEAL_KK, APPEAL_UZ)
ACCOUNT_TOPIC = union(ACCOUNT_RU, ACCOUNT_KK, ACCOUNT_UZ)
PLAYER_TOPICS = (
    (PAYMENT_TOPIC, REASON_PAYMENT_TOPIC),
    (APPEAL_TOPIC, REASON_APPEAL_TOPIC),
    (ACCOUNT_TOPIC, REASON_ACCOUNT_TOPIC),
)
DRAFT_PROMISES = (
    (union(UNBAN_PROMISE), REASON_UNBAN_PROMISE),
    (union(REFUND_PROMISE), REASON_REFUND_PROMISE),
    (union(PUNISHMENT_PROMISE), REASON_PUNISHMENT_PROMISE),
)


def normalize_text(text: str) -> str:
    return APOSTROPHES.sub("'", text.lower().replace("ё", "е"))


def matched_reasons(patterns: tuple, text: str) -> list[str]:
    return [reason for pattern, reason in patterns if pattern.search(text)]


def needs_human_guard(category: str, draft_text: str, player_text: str = "") -> list[str]:
    reasons = [REASON_ALWAYS_HUMAN] if category in ALWAYS_HUMAN else []
    reasons += matched_reasons(PLAYER_TOPICS, normalize_text(player_text))
    reasons += matched_reasons(DRAFT_PROMISES, normalize_text(draft_text))
    return reasons
