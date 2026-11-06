# Support Copilot

Сервис триажа обращений игроков Grand Mobile (Decentrathon 6.0, команда Undefined). Для каждого тикета он определяет язык, категорию и приоритет, извлекает факты (ник, сервер, номера правил, доказательства) и находит подходящие пункты правил игры. Затем готовит черновик ответа игроку с цитатами этих пунктов и решает, можно ли отправить ответ автоматически или тикет нужно передать человеку (`needs_human` с причинами). Всё доступно через `POST /triage`.

## Как это работает

```
тикет
  → classify            категория, приоритет, уверенность (правила + TF-IDF/логрегрессия)
  → extract_facts       ник, сервер, номера правил из текста, наличие доказательств
  → retrieve            поиск пунктов правил: BM25 + эмбеддинги multilingual-e5 + подсказки
                        (номера правил из текста и правила категории), слияние взвешенным RRF
  → generate_draft      черновик ответа на Gemini со structured output;
                        цитировать можно только найденные пункты
  → валидатор           цитаты должны быть из выдачи поиска, в тексте нет запрещённых обещаний
                        (разбан, возврат средств, наказание другого игрока)
  → guards              платежи, апелляции, взлом аккаунта, категории «всегда человеку»,
                        низкая уверенность, сбой генерации
  → ответ               lang, category, priority, extracted, draft_reply, needs_human, reasons
```

## Ключевые цифры

Подробности и условия замеров — в [report/retrieval_triage.md](report/retrieval_triage.md).

| Метрика | Значение |
|---|---|
| Recall@5 поиска правил (train, 5000 жалоб) | 0.558 (valid: 0.48) |
| needs_human (valid, 1000 тикетов) | 48.3% |
| Выдуманные цитаты в ответах | 0 |
| Запрещённые обещания в ответах | 0 |
| Задержка тикета без LLM, p95 | 0.25 с |
| Задержка вызова LLM, p50 | ~1 с |

## Запуск

Нужен Python 3.9.

```
python3.9 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

В `.env` задайте:

* `DATA_DIR` — абсолютный путь к папке с данными хакатона (вне репозитория);
* `RETRIEVAL_EMBEDDINGS` — `on` для гибридного поиска BM25 + эмбеддинги, `off` только для BM25;
* `GEMINI_API_KEY` — для черновиков LLM задайте GEMINI_API_KEY; без ключа сервис работает в режиме шаблонов (классификация, поиск правил и guards работают полностью);
* `DRAFT_MODEL` — модель Gemini для черновиков ответа;
* `DRAFT_RPM` — сколько вызовов LLM в минуту разрешено черновикам (по умолчанию 12): вызовы ждут свободный слот, а не получают 429;
* `JUDGE_MODEL` — модель Gemini для LLM-судьи в оценке, отличная от `DRAFT_MODEL`;
* `HF_TOKEN` — токен Hugging Face для загрузки модели эмбеддингов;
* `RRF_WEIGHT_BM25`, `RRF_WEIGHT_E5`, `RRF_WEIGHT_HINTS` — веса слияния результатов поиска (по умолчанию 1.0, 1.0, 2.0).

Команды выполняются в активированном окружении:

```
make serve
make predict IN=$DATA_DIR/tickets_valid.jsonl OUT=/tmp/pred_valid.jsonl
make test
```

`make serve` поднимает сервис на `http://localhost:8000` (`POST /triage`, `GET /health`). `make predict` пишет по строке JSON на каждый тикет: `ticket_id` и ответ `/triage`.

На бесплатном ключе Gemini `make predict` идёт примерно со скоростью `DRAFT_RPM` тикетов в минуту: в пакетном режиме вызовы ждут слот без ограничения. В `/triage` ожидание слота входит в 5 с на вызов, и если слота нет, черновик собирается по шаблону и уходит человеку.

Модель `classify` (TF-IDF по символам + логистическая регрессия) в репозитории не хранится. Она обучается при первом старте сервиса или `make predict` из `DATA_DIR/tickets_train.jsonl.gz` (около 12 с) и сохраняется в `.cache/classifier.joblib`. Без `DATA_DIR` классификация работает только на правилах, в лог пишется предупреждение. Нужен Python 3.9 и `scikit-learn==1.6.1`: модель, обученная другой версией sklearn, загружается с предупреждением и работает хуже.

## Ограничения

* **Бесплатный тариф Gemini.** Есть лимит запросов в минуту, а при перегрузке провайдер отвечает 503. В обоих случаях сервис не падает: черновик собирается по шаблону, и тикет уходит человеку с причиной «черновик не сгенерирован». Из-за этого задержка с LLM нестабильна, и в финальном прогоне при перегрузке Gemini 82% черновиков ушли в шаблон.
* **Мало kk и uz в данных.** Казахских и узбекских тикетов в выборке единицы, поэтому качество на этих языках оценено в основном на синтетических тестах.
* **Шаблоны на uz не проверены носителем.** Казахские шаблоны и формы проверены носителем, узбекские — нет.

## Оценка

Харнесс в `evaluation/` (описание в `evaluation/README.md`), отчёт в [report/README.md](report/README.md).

```
make eval            # прогон valid через /triage, метрики в results/<время>/summary.json
make eval-gold       # + accuracy категории и macro-F1 приоритета по золотому набору gold.jsonl
                     #   золотой набор (gold.jsonl) — внутренний, в репозиторий не входит
make eval-latency    # задержка без очереди (1 поток, 200 тикетов)
python -m evaluation.judge --pred results/<run>/pred.jsonl --n 40   # LLM-судья, Gemini
```

`results/`, `gold.jsonl` и таблицы с текстами игроков в репозиторий не попадают (`.gitignore`).

## Отчёт

* [report/README.md](report/README.md) — общий отчёт команды.
* [report/retrieval_triage.md](report/retrieval_triage.md) — поиск правил, валидатор цитат, needs_human, сервис `/triage` и итоговые метрики.
* [report/drafts.md](report/drafts.md) — генерация черновиков ответа.
* [report/evaluation.md](report/evaluation.md) — методика и результаты оценки.

## Источники и лицензии

### Данные

Датасет Grand Mobile × Decentrathon 6.0 (кейс Support Copilot): `tickets_train.jsonl.gz`,
`tickets_valid.jsonl`, `rules.json`, `taxonomy.json`. Используется только для решения кейса
в рамках хакатона, **в репозитории не хранится** (путь задаётся в `DATA_DIR`) и удаляется в
течение 14 дней после объявления победителей, как требуют условия.

### Модели

| Модель | Где используется | Условия |
|---|---|---|
| `gemini-3.1-flash-lite` (Google) | генерация черновиков | Gemini API, проприетарная, [Gemini API Terms](https://ai.google.dev/gemini-api/terms) |
| `gemini-3.5-flash` (Google) | LLM-судья в оценке (не часть сервиса) | то же |
| `intfloat/multilingual-e5-small` | эмбеддинги для поиска правил | MIT |

### Библиотеки

| Библиотека | Лицензия |
|---|---|
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| Pydantic | MIT |
| python-dotenv | BSD-3-Clause |
| HTTPX | BSD-3-Clause |
| pytest | MIT |
| rank-bm25 | Apache-2.0 |
| NumPy | BSD-3-Clause |
| sentence-transformers | Apache-2.0 |
| google-genai | Apache-2.0 |
| scikit-learn, joblib (`data_prep`, поиск примеров в `drafts`) | BSD-3-Clause |
| PyTorch (ставится через sentence-transformers) | BSD-3-Clause |
| transformers (ставится через sentence-transformers) | Apache-2.0 |
