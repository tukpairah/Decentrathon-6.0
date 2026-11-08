# Support Copilot

A triage service for Grand Mobile player support tickets (Decentrathon 6.0, team Undefined). For each ticket it detects the language, category and priority, extracts facts (nickname, server, rule numbers, evidence) and finds the matching game rules. It then prepares a draft reply to the player that cites those rules, and decides whether the reply can be sent automatically or the ticket must go to a human (`needs_human` with reasons). Everything is available through `POST /triage`.

## How it works

```
ticket
  → classify            category, priority, confidence (rules + TF-IDF/logistic regression)
  → extract_facts       nickname, server, rule numbers from the text, presence of evidence
  → retrieve            rule search: BM25 + multilingual-e5 embeddings + hints
                        (rule numbers from the text and category rules), merged with weighted RRF
  → generate_draft      draft reply with Gemini structured output;
                        only retrieved rules may be cited
  → validator           citations must come from the search results, the text contains no forbidden
                        promises (unban, refund, punishing another player)
  → guards              payments, appeals, account hacking, "always to a human" categories,
                        low confidence, generation failure
  → response            lang, category, priority, extracted, draft_reply, needs_human, reasons
```

## Key numbers

Details and measurement conditions are in [report/retrieval_triage.md](report/retrieval_triage.md).

| Metric | Value |
|---|---|
| Rule retrieval Recall@5 (train, 5000 complaints) | 0.558 (valid: 0.48) |
| needs_human (valid, 1000 tickets) | 48.3% |
| Fabricated citations in replies | 0 |
| Forbidden promises in replies | 0 |
| Ticket latency without LLM, p95 | 0.25 s |
| LLM call latency, p50 | ~1 s |

## Getting started

Python 3.9 is required.

```
python3.9 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set the following in `.env`:

* `DATA_DIR` — absolute path to the hackathon data folder (outside the repository);
* `RETRIEVAL_EMBEDDINGS` — `on` for hybrid BM25 + embeddings search, `off` for BM25 only;
* `GEMINI_API_KEY` — needed for LLM drafts; without a key the service runs in template mode (classification, rule retrieval and guards still work fully);
* `DRAFT_MODEL` — Gemini model for reply drafts;
* `DRAFT_RPM` — how many LLM calls per minute drafts are allowed (default 12): calls wait for a free slot instead of getting a 429;
* `JUDGE_MODEL` — Gemini model for the LLM judge in evaluation, different from `DRAFT_MODEL`;
* `HF_TOKEN` — Hugging Face token for downloading the embedding model;
* `RRF_WEIGHT_BM25`, `RRF_WEIGHT_E5`, `RRF_WEIGHT_HINTS` — weights for merging search results (defaults 1.0, 1.0, 2.0).

Commands are run inside the activated environment:

```
make serve
make predict IN=$DATA_DIR/tickets_valid.jsonl OUT=/tmp/pred_valid.jsonl
make test
```

`make serve` starts the service at `http://localhost:8000` (`POST /triage`, `GET /health`). `make predict` writes one JSON line per ticket: `ticket_id` and the `/triage` response.

On a free Gemini key, `make predict` runs at roughly `DRAFT_RPM` tickets per minute: in batch mode calls wait for a slot without a limit. In `/triage`, waiting for a slot counts toward the 5 s per call, and if no slot is free the draft is built from a template and sent to a human.

The `classify` model (character TF-IDF + logistic regression) is not stored in the repository. It is trained on the first start of the service or `make predict` from `DATA_DIR/tickets_train.jsonl.gz` (about 12 s) and saved to `.cache/classifier.joblib`. Without `DATA_DIR`, classification uses rules only and a warning is logged. Python 3.9 and `scikit-learn==1.6.1` are required: a model trained with another sklearn version loads with a warning and performs worse.

## Limitations

* **Free Gemini tier.** There is a requests-per-minute limit, and under load the provider returns 503. In both cases the service does not crash: the draft is built from a template and the ticket goes to a human with the reason "draft not generated". Because of this, latency with the LLM is unstable, and in the final run, with Gemini overloaded, 82% of drafts fell back to templates.
* **Few kk and uz tickets in the data.** Kazakh and Uzbek tickets are rare in the dataset, so quality in these languages was evaluated mostly on synthetic tests.
* **uz templates not checked by a native speaker.** Kazakh templates and forms were checked by a native speaker, Uzbek ones were not.

## Evaluation

The harness is in `evaluation/` (described in `evaluation/README.md`), the report is in [report/README.md](report/README.md).

```
make eval            # run valid through /triage, metrics in results/<time>/summary.json
make eval-gold       # + category accuracy and priority macro-F1 on the gold set gold.jsonl
                     #   the gold set (gold.jsonl) is internal and not included in the repository
make eval-latency    # latency without queueing (1 thread, 200 tickets)
python -m evaluation.judge --pred results/<run>/pred.jsonl --n 40   # LLM judge, Gemini
```

`results/`, `gold.jsonl` and tables with player texts are not committed (`.gitignore`).

## Report

* [report/README.md](report/README.md) — the team's overall report.
* [report/retrieval_triage.md](report/retrieval_triage.md) — rule retrieval, citation validator, needs_human, the `/triage` service and final metrics.
* [report/drafts.md](report/drafts.md) — reply draft generation.
* [report/evaluation.md](report/evaluation.md) — evaluation method and results.

## Sources and licenses

### Data

Grand Mobile × Decentrathon 6.0 dataset (Support Copilot case): `tickets_train.jsonl.gz`,
`tickets_valid.jsonl`, `rules.json`, `taxonomy.json`. Used only to solve the case
within the hackathon, **not stored in the repository** (the path is set in `DATA_DIR`) and deleted
within 14 days after the winners are announced, as the terms require.

### Models

| Model | Where it is used | Terms |
|---|---|---|
| `gemini-3.1-flash-lite` (Google) | draft generation | Gemini API, proprietary, [Gemini API Terms](https://ai.google.dev/gemini-api/terms) |
| `gemini-3.5-flash` (Google) | LLM judge in evaluation (not part of the service) | same |
| `intfloat/multilingual-e5-small` | embeddings for rule retrieval | MIT |

### Libraries

| Library | License |
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
| scikit-learn, joblib (`data_prep`, example search in `drafts`) | BSD-3-Clause |
| PyTorch (installed via sentence-transformers) | BSD-3-Clause |
| transformers (installed via sentence-transformers) | Apache-2.0 |
