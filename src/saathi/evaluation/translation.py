"""Per-sentence translation evaluation: quality (chrF++), time, and the runaway-guard signals."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from saathi.evaluation.metrics import chrf_pp, percentile, sentence_chrf_pp
from saathi.guard import has_repeated_phrase
from saathi.translate import TranslationResult


class StatsTranslator(Protocol):
    def translate_with_stats(self, text: str, src: str, tgt: str) -> TranslationResult: ...


@dataclass(frozen=True)
class SentenceRow:
    index: int  # position in the FLORES devtest file
    hypothesis: str
    chrf: float  # sentence-level chrF++ against the FLORES reference
    ms: float  # one translate_with_stats call, tokenization and decoding included
    input_tokens: int  # longest input row, the figure the output cap is derived from
    output_tokens: int  # longest output row, EOS included
    cap: int
    capped: bool  # the model hit the cap without finishing (a runaway)
    repeated: bool  # the repeated-phrase guard fires on the output

    @property
    def flagged(self) -> bool:
        """Would the app refuse this output as unreliable?"""
        return self.capped or self.repeated

    @property
    def ratio(self) -> float:
        return self.output_tokens / self.input_tokens if self.input_tokens else 0.0


@dataclass(frozen=True)
class ShardSummary:
    n: int
    chrf_pp: float  # corpus-level
    ms_mean: float
    ms_p50: float
    ms_p95: float
    capped: int
    repeated: int
    flagged: int


def evaluate_sentence(
    translator: StatsTranslator,
    index: int,
    source: str,
    reference: str,
    src: str,
    tgt: str,
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> SentenceRow:
    start = clock()
    result = translator.translate_with_stats(source, src, tgt)
    elapsed_ms = (clock() - start) * 1000
    return SentenceRow(
        index=index,
        hypothesis=result.text,
        chrf=sentence_chrf_pp(result.text, reference),
        ms=round(elapsed_ms, 1),
        input_tokens=result.longest_input_tokens,
        output_tokens=result.longest_output_tokens,
        cap=result.cap,
        capped=result.capped,
        repeated=has_repeated_phrase(result.text),
    )


def summarize(rows: Sequence[SentenceRow], references: Sequence[str]) -> ShardSummary:
    times = [row.ms for row in rows]
    return ShardSummary(
        n=len(rows),
        chrf_pp=chrf_pp([row.hypothesis for row in rows], references),
        ms_mean=sum(times) / len(times),
        ms_p50=percentile(times, 50),
        ms_p95=percentile(times, 95),
        capped=sum(row.capped for row in rows),
        repeated=sum(row.repeated for row in rows),
        flagged=sum(row.flagged for row in rows),
    )


def ratio_summary(rows: Sequence[SentenceRow]) -> tuple[float, float, float]:
    """Output/input token ratio: p50, p95 and max. Real translations should sit well under 2."""
    ratios = [row.ratio for row in rows]
    return percentile(ratios, 50), percentile(ratios, 95), max(ratios)
