"""Scoring of STT transcripts against the known text the speaker read or the TTS spoke."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from saathi.evaluation.metrics import cer, chrf_pp, normalize
from saathi.evaluation.startclip import HeadTail, head_tail_misses


@dataclass(frozen=True)
class SttRow:
    index: int  # FLORES devtest index of the sentence
    transcript: str
    cer: float
    head_words: int
    head_missed: int
    tail_words: int
    tail_missed: int

    @property
    def head_tail(self) -> HeadTail:
        return HeadTail(self.head_words, self.head_missed, self.tail_words, self.tail_missed)


@dataclass(frozen=True)
class SttSummary:
    n: int
    cer_mean: float
    cer_median: float
    chrf_pp: float  # corpus-level, on normalized text
    head_words: int
    head_missed: int
    head_rate: float
    tail_words: int
    tail_missed: int
    tail_rate: float


def score_transcript(index: int, transcript: str, reference: str) -> SttRow:
    totals = head_tail_misses(reference, transcript)
    return SttRow(
        index=index,
        transcript=transcript,
        cer=cer(transcript, reference),
        head_words=totals.head_words,
        head_missed=totals.head_missed,
        tail_words=totals.tail_words,
        tail_missed=totals.tail_missed,
    )


def summarize_stt(rows: Sequence[SttRow], references: Sequence[str]) -> SttSummary:
    """`references` line up with `rows`. chrF++ is computed on normalized text."""
    totals = sum((row.head_tail for row in rows), HeadTail())
    return SttSummary(
        n=len(rows),
        cer_mean=statistics.fmean(row.cer for row in rows),
        cer_median=statistics.median(row.cer for row in rows),
        chrf_pp=chrf_pp(
            [normalize(row.transcript) for row in rows], [normalize(r) for r in references]
        ),
        head_words=totals.head_words,
        head_missed=totals.head_missed,
        head_rate=totals.head_rate,
        tail_words=totals.tail_words,
        tail_missed=totals.tail_missed,
        tail_rate=totals.tail_rate,
    )
