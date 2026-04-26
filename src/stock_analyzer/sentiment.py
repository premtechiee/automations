"""
stock_analyzer/sentiment.py
============================
Categorised headline sentiment.

For every headline that mentions the ticker we classify hits across multiple
*categories* (earnings, corp_action, shareholder, regulatory, political,
geopolitical, macro). Each category produces its own +/- counts so the
self-learning module can attribute outcomes to specific drivers.

Returned dict shape::

    {
        "score":     63.2,       # overall 0..100 (50 = neutral)
        "matched":   7,          # headlines mentioning the ticker
        "pos":       4,          # total positive keyword hits
        "neg":       2,          # total negative keyword hits
        "categories": {
            "earnings":     {"pos": 2, "neg": 0, "score": 75.0},
            "regulatory":   {"pos": 1, "neg": 1, "score": 50.0},
            ...
        },
        "samples":   [up to 3 matched headlines]
    }

Backward compatible: callers that only read `score` keep working.
"""

from __future__ import annotations
import logging

from .config import POS_WORDS, NEG_WORDS, SENTIMENT_CATEGORIES

logger = logging.getLogger(__name__)


def _tokenise(headline: str) -> set[str]:
    """Lower-case word/phrase tokens. Two-word combos joined by '-' so phrases
    like 'rate-cut', 'fii-inflow' match cleanly."""
    raw = [w.strip(".,:;!?\"'()[]{}").lower() for w in headline.split()]
    raw = [w for w in raw if w]
    pairs = [f"{a}-{b}" for a, b in zip(raw, raw[1:])]
    return set(raw) | set(pairs)


def score_headlines_for(keyword: str, headlines: list[str]) -> dict:
    kw = keyword.lower()
    matched = [h for h in headlines if kw in h.lower()]
    if not matched:
        return {
            "score": 50.0, "matched": 0, "pos": 0, "neg": 0,
            "categories": {}, "samples": [],
        }

    cat_counts: dict[str, dict[str, int]] = {
        c: {"pos": 0, "neg": 0} for c in SENTIMENT_CATEGORIES
    }
    flat_pos = flat_neg = 0
    for h in matched:
        toks = _tokenise(h)
        # Per-category attribution
        for cat, kws in SENTIMENT_CATEGORIES.items():
            cat_counts[cat]["pos"] += len(toks & kws["pos"])
            cat_counts[cat]["neg"] += len(toks & kws["neg"])
        # Flat fallback (legacy POS_WORDS/NEG_WORDS for general optimism words)
        flat_pos += len(toks & POS_WORDS)
        flat_neg += len(toks & NEG_WORDS)

    if flat_pos + flat_neg == 0:
        score = 50.0
    else:
        norm = (flat_pos - flat_neg) / (flat_pos + flat_neg)
        score = (norm + 1) * 50

    cat_scores: dict[str, dict] = {}
    for cat, c in cat_counts.items():
        if c["pos"] + c["neg"] == 0:
            continue
        cn = (c["pos"] - c["neg"]) / (c["pos"] + c["neg"])
        cat_scores[cat] = {
            "pos":   c["pos"],
            "neg":   c["neg"],
            "score": round((cn + 1) * 50, 1),
        }

    return {
        "score":      round(score, 1),
        "matched":    len(matched),
        "pos":        flat_pos,
        "neg":        flat_neg,
        "categories": cat_scores,
        "samples":    matched[:3],
    }
