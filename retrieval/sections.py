SECTION_CODES: dict[int, str] = {
    30: "ОП",
    31: "ЖБ",
    32: "GZ",
    33: "ЛД",
    34: "ГО",
    35: "ГВ",
    36: "СМ",
    40: "ОПГ",
    41: "ВБ",
    42: "БФ",
}

SECTION_TITLES: dict[str, str] = {
    "ОП": "Общие правила",
    "ЖБ": "Правила жалоб",
    "GZ": "Зелёная зона",
}

CANONICAL_CODES = frozenset(SECTION_CODES.values())

CODE_ALIASES: dict[str, str] = {
    "OP": "ОП",
    "JB": "ЖБ",
    "ZB": "ЖБ",
    "LD": "ЛД",
    "GO": "ГО",
    "GV": "ГВ",
    "SM": "СМ",
    "OPG": "ОПГ",
    "VB": "ВБ",
    "BF": "БФ",
    "ГЗ": "GZ",
}

PHRASE_CODES: tuple[tuple[str, str], ...] = (
    (r"общ\w*\s+правил", "ОП"),
    (r"правил\w*\s+жалоб", "ЖБ"),
    (r"зелен\w*\s+зон", "GZ"),
)
