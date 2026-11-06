"""Детерминированные ответы без LLM: пустые репорты, передача человеку, запасной вариант.

kk проверено носителем. uz написаны вручную и ТРЕБУЮТ проверки носителем до показа жюри.
"""

T = {
    "ru": {
        "empty_report": "Здравствуйте! Опишите, пожалуйста, ваш вопрос или проблему подробнее, и мы постараемся помочь.",
        "handoff": "Здравствуйте! Ваше обращение передано специалисту, он свяжется с вами после проверки.",
        "complaint_fallback": "Здравствуйте! Ваша жалоба принята и передана на рассмотрение администрации. Решение будет принято после проверки.",
        "no_evidence": "Здравствуйте! Для рассмотрения жалобы приложите доказательства (скриншоты или видео) и подайте её повторно.",
    },
    "kk": {
        "empty_report": "Сәлеметсіз бе! Сұрағыңызды немесе мәселеңізді толығырақ жазыңыз, көмектесуге тырысамыз.",
        "handoff": "Сәлеметсіз бе! Өтінішіңіз маманға жіберілді, ол тексеріп болған соң сізбен хабарласады.",
        "complaint_fallback": "Сәлеметсіз бе! Шағымыңыз қабылданып, әкімшілікке қарауға жіберілді. Тексеру аяқталған соң шешім шығарылады.",
        "no_evidence": "Сәлеметсіз бе! Шағымыңызды қарауымыз үшін дәлел (скриншот немесе видео) тіркеп, қайта жіберіңіз.",
    },
    "uz": {
        "empty_report": "Assalomu alaykum! Savol yoki muammoingizni batafsilroq yozing, yordam berishga harakat qilamiz.",
        "handoff": "Assalomu alaykum! Murojaatingiz mutaxassisga yuborildi, tekshiruvdan so‘ng siz bilan bog‘lanadi.",
        "complaint_fallback": "Assalomu alaykum! Shikoyatingiz qabul qilindi va ma’muriyatga ko‘rib chiqish uchun yuborildi. Qaror tekshiruvdan keyin qabul qilinadi.",
        "no_evidence": "Assalomu alaykum! Shikoyatni ko‘rib chiqish uchun dalillarni (skrinshot yoki video) qo‘shib, qayta yuboring.",
    },
    "en": {
        "empty_report": "Hello! Please describe your question or problem in more detail and we will try to help.",
        "handoff": "Hello! Your request has been passed to a specialist who will get back to you after reviewing it.",
        "complaint_fallback": "Hello! Your complaint has been received and sent to the administration for review. A decision will be made after the check.",
        "no_evidence": "Hello! To review your complaint, please attach evidence (screenshots or video) and submit it again.",
    },
}


def tpl(lang, key):
    return T.get(lang, T["ru"])[key]
