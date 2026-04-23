"""
stock_analyzer/sentiment.py
============================
Very light-weight sentiment: count positive/negative keywords in
recent RSS headlines that mention the ticker or its root name.
Returns 0..100 where 50 = neutral.

This is deliberately simple — no external LLM or paid API.
"""

from __future__ import annotations
import logging

from .config import POS_WORDS, NEG_WORDS

logger = logging.getLogger(__name__)


def score_headlines_for(keyword: str, headlines: list[str]) -> dict:
    kw = keyword.lower()
    matched = [h for h in headlines if kw in h.lower()]
    if not matched:
        return {"score": 50.0, "matched": 0, "pos": 0, "neg": 0, "samples": []}

    pos = neg = 0
    for h in matched:
        words = {w.strip(".,:;!?\"'()[]").lower() for w in h.split()}
        pos += len(words & POS_WORDS)
        neg += len(words & NEG_WORDS)

    if pos + neg == 0:
        score = 50.0
    else:
        # −1 … +1 normalised then mapped to 0 … 100
        norm = (pos - neg) / (pos + neg)
        score = (norm + 1) * 50

    return {
        "score":   round(score, 1),
        "matched": len(matched),
        "pos":     pos,
        "neg":     neg,
        "samples": matched[:3],
    }
