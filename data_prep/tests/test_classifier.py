from data_prep.classifier import normalize_text, detect_language, normalize_violation, classify, extract_facts, is_spam_or_duplicate
from app.schemas import Message, TriageRequest

def request(text, kind='complaint', attachments=0):
    return TriageRequest(kind=kind, messages=[Message(role='player', text=text, attachments=attachments)])

def test_cp1251():
    assert normalize_text('Привет'.encode('cp1251')) == 'Привет'

def test_languages():
    assert detect_language('Здравствуйте, помогите') == 'ru'
    assert detect_language('Olá jogador, minha conta') == 'pt'
    assert detect_language('salam magan komek kerek') == 'kk'
    assert detect_language('please help with my account') == 'en'

def test_violation():
    assert normalize_violation('читы') == 'complaint.cheat'

def test_classify():
    cat, priority, confidence = classify(request('Игрок использует читы'))
    assert cat == 'complaint.cheat' and 0 <= confidence <= 1

def test_extract():
    facts = extract_facts(request('Ник: Player_12, сервер: 5, нарушил 2.1 ОП, видео', attachments=1))
    assert facts.nickname == 'Player_12' and facts.rule_refs == ['2.1 ОП'] and facts.has_evidence

def test_duplicate():
    req = TriageRequest(kind='report', messages=[Message(role='player',text='same'),Message(role='player',text='same')])
    assert is_spam_or_duplicate(req)
