"""Text-quality and latency statistics."""

import random
import unicodedata
from collections.abc import Sequence

from sacrebleu.metrics.chrf import CHRF

# chrF++ = chrF with word bigrams (word_order=2), the metric the IndicTrans2 paper reports.
_CHRF_PP = CHRF(word_order=2)


def normalize(text: str) -> str:
    """NFC, punctuation removed, whitespace collapsed, case folded.

    Applied to STT outputs and their references before CER, chrF and word matching, so that the
    score measures what was heard rather than the punctuation and Unicode form Prisma chose.
    Punctuation becomes a space (not nothing) so that "a-b" stays two words.
    """
    composed = unicodedata.normalize("NFC", text)
    spaced = "".join(" " if unicodedata.category(c).startswith("P") else c for c in composed)
    return " ".join(spaced.split()).casefold()


def chrf_pp(hypotheses: Sequence[str], references: Sequence[str]) -> float:
    """Corpus-level chrF++ (0-100), one reference per hypothesis."""
    if len(hypotheses) != len(references):
        raise ValueError("hypotheses and references must have the same length")
    return float(_CHRF_PP.corpus_score(list(hypotheses), [list(references)]).score)


def sentence_chrf_pp(hypothesis: str, reference: str) -> float:
    return float(_CHRF_PP.sentence_score(hypothesis, [reference]).score)


def edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    """Levenshtein distance between two sequences."""
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            cost = 0 if item_a == item_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def cer(hypothesis: str, reference: str) -> float:
    """Character error rate after normalization. Can exceed 1.0 when the hypothesis is longer."""
    ref = normalize(reference)
    if not ref:
        raise ValueError("reference is empty after normalization")
    return edit_distance(normalize(hypothesis), ref) / len(ref)


def bootstrap_mean_ci(
    values: Sequence[float], *, resamples: int = 2000, seed: int = 0
) -> tuple[float, float, float]:
    """Mean and 95% bootstrap confidence interval (fixed seed, so reruns agree)."""
    if not values:
        raise ValueError("no values")
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(resamples))
    return sum(values) / n, means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def percentile(values: Sequence[float], q: float) -> float:
    """The q-th percentile (0-100) by linear interpolation between closest ranks."""
    if not values:
        raise ValueError("no values")
    if not 0 <= q <= 100:
        raise ValueError("q must be between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
