"""Few-shot из реальных ответов админов train: поиск похожих тикетов по символьным n-граммам TF-IDF.

Данные читаются из DATA_DIR (вне репозитория). Индекс кэшируется в DATA_DIR/.cache, не в репо.
Ники в ответах заменяются на {reporter} / {reported}, чтобы не тащить чужие имена в черновик.
"""
import gzip
import json
import os
import pickle
import re

from . import config

_NICK = re.compile(r"\b[A-Z][a-z]+_[A-Z][a-z]+\d*\b")
_DIGITS_TOK = re.compile(r"#?<digits>")


def _anon_reply(reply, reported_nick):
    t = reply
    if reported_nick:
        t = t.replace(reported_nick, "{reported}")
    first = _NICK.search(t)
    if first:
        t = t.replace(first.group(0), "{reporter}")
    t = _NICK.sub("{reported}", t)
    t = _DIGITS_TOK.sub("", t)
    t = re.sub(r"\s-(?=[^\W\d_])", " ", t)  # остаток от «#<digits>-shikoyat…»
    t = t.replace("{reporter}", "").replace("{reported}", "…")  # без плейсхолдеров в примерах
    t = re.sub(r"\s+,", ",", t)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{2,}", "\n", t)).strip()


def _player_text(r):
    return " ".join(m["text"] for m in r["messages"] if m["role"] == "player").strip()


def _admin_reply(r):
    a = [m["text"] for m in r["messages"] if m["role"] == "admin"]
    return a[-1] if a else ""


class ExampleIndex:
    def __init__(self, vec, mat, items):
        self.vec, self.mat, self.items = vec, mat, items

    @classmethod
    def build(cls, train_path=None, limit=None):
        from sklearn.feature_extraction.text import TfidfVectorizer
        train_path = train_path or os.path.join(config.DATA_DIR, "tickets_train.jsonl.gz")
        items, seen = [], set()
        with gzip.open(train_path, "rt", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if limit and i >= limit:
                    break
                r = json.loads(line)
                q, a = _player_text(r), _admin_reply(r)
                if not q or not a or len(a) > 600 or len(q) > 400:
                    continue
                a = _anon_reply(a, r.get("reported_nick"))
                key = (r["kind"], q.lower()[:60], a[:60])
                if key in seen:
                    continue
                seen.add(key)
                items.append({"kind": r["kind"], "lang": r.get("lang", "und"), "verdict": r.get("verdict"),
                              "player": q, "reply": a})
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, min_df=2, max_features=300_000)
        mat = vec.fit_transform([x["player"] for x in items])
        return cls(vec, mat, items)

    @classmethod
    def load(cls, cache=None, **kw):
        cache = cache or os.path.join(config.DATA_DIR, ".cache", "examples.pkl")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return cls(*pickle.load(f))
        idx = cls.build(**kw)
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "wb") as f:
            pickle.dump((idx.vec, idx.mat, idx.items), f)
        return idx

    def search(self, text, kind, lang="ru", k=None, verdict=None):
        """k ближайших по тексту игрока ответов админов того же kind; тот же язык в приоритете."""
        k = k or config.MAX_EXAMPLES
        sims = (self.mat @ self.vec.transform([text or ""]).T).toarray().ravel()
        order = sims.argsort()[::-1]
        out = []
        for i in order[:400]:
            it = self.items[i]
            if it["kind"] != kind or sims[i] <= 0:
                continue
            if lang in ("kk", "uz") and it["lang"] != lang and len(out) < 1:
                pass  # kk/uz примеров мало: берём лучшие любого языка, но язык ответа задаёт промпт
            if verdict and it["verdict"] not in (verdict, None):
                continue
            out.append({"player": it["player"][:config.EXAMPLE_CHARS], "reply": it["reply"][:config.EXAMPLE_CHARS]})
            if len(out) == k:
                break
        return out
