"""
Sentence-window chunking, to fight whole-message dilution.

FAILURE_ANALYSIS.md scenario 1: a short injected instruction embedded inside
a longer benign message (e.g. a "document" to summarize) scores confidently
benign when the whole message is embedded as one vector -- the injection's
signal gets averaged away by surrounding benign content. Root cause isn't a
threshold problem, it's a granularity problem: embed smaller windows instead
of the whole message, and take the max, so a 2-sentence injection can't be
diluted by the other 8 sentences it's sitting next to.

This is deliberately cheap (regex sentence splitting, not a real sentence
tokenizer) -- good enough to test the hypothesis, not a production parser.
"""
import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def chunk_text(text: str, window: int = 2, min_chars: int = 12) -> list[str]:
    """Sliding window over sentences, `window` sentences per chunk.

    Returns [] for single-sentence text -- nothing to gain from chunking a
    message that's already one unit, and it would just duplicate the
    whole-message candidate the caller already scores.
    """
    sentences = split_sentences(text)
    if len(sentences) <= 1:
        return []

    chunks = []
    for i in range(len(sentences)):
        chunk = " ".join(sentences[i:i + window])
        if len(chunk) >= min_chars:
            chunks.append(chunk)
    return chunks
