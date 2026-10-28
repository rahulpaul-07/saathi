"""Text-only scoring of the fact extractor against the synthetic gold set. No network, no Gnani.

Per fact type: a predicted fact is correct when a gold fact of the same kind has the same value
(case, ZWJ and other spelling folds applied by `facts.text.key`). Ambiguous predictions are
surfaced as heard, not asserted, so they stay out of precision and count as a miss for recall;
they are reported separately, with whether their candidate reading matched the gold.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from saathi.facts import FACT_KINDS, Fact, FactKind, extract_facts
from saathi.facts.text import key

Split = Literal["dev", "test", "all"]


@dataclass(frozen=True)
class GoldFact:
    kind: FactKind
    value: str


@dataclass(frozen=True)
class GoldUtterance:
    id: str
    split: Literal["dev", "test"]
    lang: str
    text: str
    facts: tuple[GoldFact, ...]


@dataclass
class KindScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    ambiguous: int = 0  # predictions shown as heard instead of asserted
    ambiguous_reading_correct: int = 0

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None


@dataclass
class Report:
    by_kind: dict[FactKind, KindScore] = field(default_factory=dict)
    utterances: int = 0
    all_correct: int = 0  # utterances whose facts were all found with no wrong extra

    @property
    def overall(self) -> KindScore:
        total = KindScore()
        for score in self.by_kind.values():
            total.tp += score.tp
            total.fp += score.fp
            total.fn += score.fn
            total.ambiguous += score.ambiguous
            total.ambiguous_reading_correct += score.ambiguous_reading_correct
        return total


def _norm(value: str) -> str:
    return " ".join(key(word) for word in value.split())


def load_gold(path: Path) -> list[GoldUtterance]:
    data = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    utterances: list[GoldUtterance] = []
    for item in data["utterances"]:
        facts = tuple(GoldFact(f["kind"], f["value"]) for f in item["facts"])
        utterances.append(
            GoldUtterance(item["id"], item["split"], item["lang"], item["text"], facts)
        )
    return utterances


def select(utterances: list[GoldUtterance], split: Split) -> list[GoldUtterance]:
    return [u for u in utterances if split == "all" or u.split == split]


def _score_utterance(
    gold: GoldUtterance, predicted: list[Fact], report: Report
) -> tuple[list[Fact], list[GoldFact], list[Fact]]:
    """Update the report; return (wrong predictions, missed gold facts, ambiguous predictions)."""
    unmatched = list(gold.facts)
    wrong: list[Fact] = []
    ambiguous = [fact for fact in predicted if fact.ambiguous]
    for fact in predicted:
        if fact.ambiguous:
            continue
        score = report.by_kind.setdefault(fact.kind, KindScore())
        match = next(
            (g for g in unmatched if g.kind == fact.kind and _norm(g.value) == _norm(fact.value)),
            None,
        )
        if match is None:
            score.fp += 1
            wrong.append(fact)
        else:
            score.tp += 1
            unmatched.remove(match)
    for fact in ambiguous:
        score = report.by_kind.setdefault(fact.kind, KindScore())
        score.ambiguous += 1
        reading = fact.reading or ""
        if any(g.kind == fact.kind and _norm(g.value) == _norm(reading) for g in unmatched):
            score.ambiguous_reading_correct += 1
    for missed in unmatched:
        report.by_kind.setdefault(missed.kind, KindScore()).fn += 1
    return wrong, unmatched, ambiguous


@dataclass(frozen=True)
class Miss:
    utterance: GoldUtterance
    wrong: list[Fact]
    missed: list[GoldFact]
    ambiguous: list[Fact]


def score_transcript(gold: GoldUtterance, transcript: str) -> Report:
    """Score the facts extracted from an STT transcript against one gold utterance."""
    report = Report(utterances=1)
    wrong, missed, _ = _score_utterance(gold, extract_facts(transcript, gold.lang), report)
    report.all_correct = 0 if wrong or missed else 1
    for kind in FACT_KINDS:
        report.by_kind.setdefault(kind, KindScore())
    return report


def score(utterances: list[GoldUtterance]) -> tuple[Report, list[Miss]]:
    """Run the extractor on each gold text. Returns the report and the utterances with errors."""
    report = Report()
    misses: list[Miss] = []
    for gold in utterances:
        predicted = extract_facts(gold.text, gold.lang)
        wrong, missed, ambiguous = _score_utterance(gold, predicted, report)
        report.utterances += 1
        if wrong or missed:
            misses.append(Miss(gold, wrong, missed, ambiguous))
        else:
            report.all_correct += 1
    for kind in FACT_KINDS:
        report.by_kind.setdefault(kind, KindScore())
    return report, misses
