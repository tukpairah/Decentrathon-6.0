"""Train a lightweight char-ngram model using player-only, high-confidence labels."""
import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from .classifier import MODEL_PATH, normalize_text, normalize_violation, weak_label


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', default=str(MODEL_PATH))
    ap.add_argument('--max-features', type=int, default=30000)
    ap.add_argument('--min-confidence', type=float, default=0.66)
    args = ap.parse_args()
    train(args.input, args.output, args.max_features, args.min_confidence, log=print)


def train(input_path, output_path, max_features=30000, min_confidence=0.66, log=None):
    """Обучает модель по JSONL (можно .gz) и сохраняет её в output_path. Возвращает число обучающих тикетов."""
    log = log or (lambda *parts: None)

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    import joblib

    texts, labels = [], []
    opener = gzip.open if str(input_path).endswith('.gz') else open
    with opener(input_path, 'rt', encoding='utf-8') as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            kind = row.get('kind', 'complaint')
            # Admin replies can contain the answer: never train on them.
            text = normalize_text(row.get('text') or ' '.join(
                m.get('text', '') for m in row.get('messages', [])
                if m.get('role', '').lower() != 'admin'
            ))
            label = normalize_violation(row.get('category') or row.get('violation'), kind)
            if label:
                conf = 1.0
            else:
                label, conf = weak_label(text, kind)
            if text and conf >= min_confidence and label not in ('complaint.other', 'report.offtopic'):
                texts.append(text)
                labels.append(label)

    if len(set(labels)) < 2:
        raise ValueError('Need at least two labeled classes')
    log('Pseudo-label distribution:', dict(Counter(labels)))
    model = make_pipeline(
        TfidfVectorizer(analyzer='char', ngram_range=(2, 4), min_df=3,
                        max_features=max_features, dtype=__import__('numpy').float32),
        LogisticRegression(max_iter=500, class_weight='balanced'),
    )
    model.fit(texts, labels)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output, compress=3)
    log(f'Trained on {len(texts)} tickets, {len(set(labels))} classes; saved {output}')
    log(f'Model size: {output.stat().st_size / 1024 / 1024:.2f} MiB')
    return len(texts)


if __name__ == '__main__':
    main()
