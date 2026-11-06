# Даня — данные и классификация

Implemented in `data_prep/classifier.py` and wired to `app/interfaces.py` without changing the `/triage` contract.

- Unicode NFKC and CP1251 byte normalization; heuristic `ru`, `kk` (Cyrillic or Latin), `pt`, `en` detection.
- `violation` aliases and weak labeling by category-specific keywords.
- Category and priority classification with confidence, optional local character n-gram TF-IDF + logistic regression model.
- Nickname, server, rule reference and evidence extraction; repeated-message and obvious spam detection.

## Optional supervised training

Prepare a UTF-8 JSONL file with one ticket per line, e.g. `{"kind":"complaint","text":"Игрок использует читы","category":"complaint.cheat"}`. With at least two classes:

```bash
pip install -r requirements.txt
python -m data_prep.train --input labeled_tickets.jsonl
pytest -q data_prep/tests
```

If no model file exists, deterministic weak-label heuristics are used. Confidence for ambiguous/unseen tickets is intentionally low, so the existing pipeline sends them to human review. The project archive contains no labeled training corpus, so supervised model accuracy cannot be claimed. Language detection and spam detection are heuristic; production evaluation on real multilingual tickets is needed.
