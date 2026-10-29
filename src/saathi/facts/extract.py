"""Rule-based extraction of gate, floor, cross, main, block, flat and landmark from a transcript.

Biased to precision: a missing fact beats a wrong one. Structured facts come first (a trigger word
next to a value); landmarks are found afterwards from what is left. See docs/DESIGN.md section 8
and the probe findings in docs/DECISIONS.md.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from saathi.facts.lexicon import Lexicon
from saathi.facts.lexicons import lexicon_for
from saathi.facts.numbers import Number, joined, parse_letter, parse_number
from saathi.facts.text import Token, tokenize
from saathi.facts.types import Confidence, Fact, FactKind
from saathi.languages import LANGUAGES

Stops = Callable[[int], bool]  # does token `index` end a landmark name?

MAX_TEXT_CHARS = 2000  # same cap as translation input
_MAX_LANDMARK_TOKENS = 4
# Probe: en-IN STT wrote "fourth floor" as "1/4 floor".
_FRACTION = re.compile(r"1/(\d{1,2})")


@dataclass(frozen=True)
class _Spec:
    max_value: int  # larger values are read as STT noise, not a gate or a floor
    trigger_first: bool  # "gate 2": the value follows the trigger
    value_first: bool  # "2nd cross": the value precedes the trigger
    value_first_needs_filler: bool = False  # "2 number gate" yes, "2 gate" no
    letters: bool = False  # the value may carry a label such as 5B
    letter_alone: bool = False  # the value may be just a label: "Block C", "ಟವರ್ ಬಿ"
    fraction: bool = False  # accept the probe's "1/4 floor" misreading


_SPECS: dict[FactKind, _Spec] = {
    "gate": _Spec(99, trigger_first=True, value_first=True, value_first_needs_filler=True),
    "flat": _Spec(9999, trigger_first=True, value_first=False, letters=True),
    "block": _Spec(99, trigger_first=True, value_first=False, letters=True, letter_alone=True),
    "cross": _Spec(99, trigger_first=False, value_first=True),
    "main": _Spec(99, trigger_first=False, value_first=True),
    "floor": _Spec(60, trigger_first=False, value_first=True, fraction=True),
}
# Lower number = claimed first. A trigger-first value ("gate 2") and anything introduced by an
# explicit filler ("2 number gate") beat a bare value-first guess, which beats a bare value after.
_PRIORITY_EXPLICIT, _PRIORITY_VALUE_FIRST, _PRIORITY_VALUE_AFTER = 0, 1, 2


@dataclass(frozen=True)
class _Candidate:
    priority: int
    kind: FactKind
    first: int  # token range of the whole phrase, inclusive
    last: int
    number_first: int  # token range of the value alone
    number_last: int
    number: str  # the value to report when the reading is clear
    reading: str | None  # candidate reading when ambiguous
    confidence: Confidence

    @property
    def span(self) -> range:
        return range(self.first, self.last + 1)


def _within_range(kind: FactKind, magnitude: int) -> bool:
    return magnitude <= _SPECS[kind].max_value


def _after_candidates(
    tokens: list[Token], trigger: int, kind: FactKind, lex: Lexicon
) -> list[_Candidate]:
    """Value after the trigger: "gate number 2", "ಗೇಟ್ ನಂಬರ್ ಎರಡು", "block C"."""
    spec = _SPECS[kind]
    if trigger + 1 >= len(tokens) or tokens[trigger].break_after:
        return []
    start = trigger + 1
    filler = tokens[start].key in lex.fillers and joined(tokens, start)
    if filler:
        start += 1
    number = parse_number(tokens, start, lex, allow_letter=spec.letters)
    if number is not None and _within_range(kind, number.magnitude):
        priority = _PRIORITY_EXPLICIT if spec.trigger_first else _PRIORITY_VALUE_AFTER
        return [_build(kind, tokens, trigger, start, number, priority)]
    if spec.letter_alone:
        letter = parse_letter(tokens, start, lex)
        if letter:
            return [_build(kind, tokens, trigger, start, Number(letter, start + 1), 0)]
    return []


def _before_candidates(
    tokens: list[Token], trigger: int, kind: FactKind, lex: Lexicon
) -> list[_Candidate]:
    """Value before the trigger: "2nd cross", "ಎರಡನೇ ಕ್ರಾಸ್", "দুই নম্বর ক্রস", "1/4 floor"."""
    spec = _SPECS[kind]
    end = trigger  # exclusive end of the number
    filler = end >= 1 and tokens[end - 1].key in lex.fillers and not tokens[end - 1].break_after
    if filler:
        end -= 1
    if end < 1 or tokens[end - 1].break_after or (filler and tokens[end].break_after):
        return []
    if spec.value_first_needs_filler and not filler:
        return []
    if spec.fraction and not filler:
        fraction = _FRACTION.fullmatch(tokens[end - 1].key)
        if fraction and int(fraction[1]) <= spec.max_value:
            return [
                _build(kind, tokens, trigger, end - 1, Number(str(int(fraction[1])), end), 1, "low")
            ]
    for start in range(max(0, end - 5), end):  # the longest number that ends exactly at `end`
        number = parse_number(tokens, start, lex)
        if number is not None and number.end == end:
            if not _within_range(kind, number.magnitude):
                return []
            priority = _PRIORITY_EXPLICIT if filler else _PRIORITY_VALUE_FIRST
            return [_build(kind, tokens, trigger, start, number, priority)]
    return []


def _build(
    kind: FactKind,
    tokens: list[Token],
    trigger: int,
    number_first: int,
    number: Number,
    priority: int,
    confidence: Confidence = "high",
) -> _Candidate:
    number_last = number.end - 1
    members = [trigger, number_first, number_last]
    # A filler between trigger and value lies inside [first, last]: the three parts are contiguous.
    return _Candidate(
        priority=priority,
        kind=kind,
        first=min(members),
        last=max(members),
        number_first=number_first,
        number_last=number_last,
        number=number.value,
        reading=number.value if number.ambiguous else None,
        confidence=confidence,
    )


def _structured(tokens: list[Token], lex: Lexicon, text: str) -> tuple[list[Fact], set[int]]:
    candidates: list[tuple[int, _Candidate]] = []
    for index, token in enumerate(tokens):
        kind = lex.triggers.get(token.key)
        if kind is None:
            continue
        found = _after_candidates(tokens, index, kind, lex)
        if _SPECS[kind].value_first:
            found += _before_candidates(tokens, index, kind, lex)
        candidates.extend((index, candidate) for candidate in found)

    used: set[int] = set()
    facts: list[Fact] = []
    for _, candidate in sorted(candidates, key=lambda item: (item[1].priority, item[0])):
        if used.intersection(candidate.span):
            continue
        used.update(candidate.span)
        facts.append(_to_fact(candidate, tokens, text))
    return facts, used


def _to_fact(candidate: _Candidate, tokens: list[Token], text: str) -> Fact:
    start, end = tokens[candidate.first].start, tokens[candidate.last].end
    heard = text[start:end]
    value_start = tokens[candidate.number_first].start
    value_end = tokens[candidate.number_last].end
    if candidate.reading is None:
        return Fact(
            candidate.kind, candidate.number, start, end, heard, candidate.confidence,
            value_start=value_start, value_end=value_end,
        )  # fmt: skip
    # Ambiguous: surface the number words as heard; the joined digits are only a candidate.
    return Fact(
        candidate.kind, text[value_start:value_end], start, end, heard, candidate.confidence,
        ambiguous=True, reading=candidate.reading, value_start=value_start, value_end=value_end,
    )  # fmt: skip


def _match_at(tokens: list[Token], index: int, phrase: tuple[str, ...]) -> bool:
    if index + len(phrase) > len(tokens):
        return False
    for offset, word in enumerate(phrase):
        if tokens[index + offset].key != word:
            return False
        if offset < len(phrase) - 1 and tokens[index + offset].break_after:
            return False
    return True


def _landmarks(tokens: list[Token], lex: Lexicon, used: set[int], text: str) -> list[Fact]:
    first_words = {phrase[0] for phrase in lex.landmark_before | lex.landmark_after}

    def stops(index: int) -> bool:
        key = tokens[index].key
        return (
            index in used
            or key in lex.stopwords
            or key in lex.fillers  # "gate number" whose value was not understood is not a name
            or key in first_words
            or key[:1].isdigit()  # a value the structured pass could not read: do not swallow it
        )

    facts: list[Fact] = []
    index = 0
    while index < len(tokens):
        before = _longest_match(tokens, index, lex.landmark_before)
        after = _longest_match(tokens, index, lex.landmark_after)
        if before:
            span = _collect_forward(tokens, index + len(before), stops)
            confidence: Confidence = "high"
            skip = len(before)
        elif after:
            span = _collect_backward(tokens, index, stops)
            confidence = "low"  # open-ended: the name is whatever precedes the postposition
            skip = len(after)
        else:
            index += 1
            continue
        span = _trim(tokens, span, lex)
        if span:
            used.update(span)
            start, end = tokens[span[0]].start, tokens[span[-1]].end
            facts.append(Fact("landmark", text[start:end], start, end, text[start:end], confidence))
        index += skip
    return facts


def _longest_match(
    tokens: list[Token], index: int, phrases: frozenset[tuple[str, ...]]
) -> tuple[str, ...] | None:
    matches = [phrase for phrase in phrases if _match_at(tokens, index, phrase)]
    return max(matches, key=len) if matches else None


def _collect_forward(tokens: list[Token], start: int, stops: Stops) -> list[int]:
    if tokens[start - 1].break_after:
        return []
    span: list[int] = []
    index = start
    while index < len(tokens) and len(span) < _MAX_LANDMARK_TOKENS and not stops(index):
        span.append(index)
        if tokens[index].break_after:
            break
        index += 1
    return span


def _collect_backward(tokens: list[Token], trigger: int, stops: Stops) -> list[int]:
    if trigger == 0 or tokens[trigger - 1].break_after:
        return []
    span: list[int] = []
    index = trigger - 1
    while index >= 0 and len(span) < _MAX_LANDMARK_TOKENS and not stops(index):
        span.insert(0, index)
        if index == 0 or tokens[index - 1].break_after:
            break
        index -= 1
    return span


def _trim(tokens: list[Token], span: list[int], lex: Lexicon) -> list[int]:
    while span and tokens[span[0]].key in lex.leading_particles:
        span = span[1:]
    while span and tokens[span[-1]].key in lex.trailing_particles:
        span = span[:-1]
    return span


def extract_facts(text: str, language: str) -> list[Fact]:
    """Facts in `text`, a transcript in `language` (a code from `LANGUAGES`), ordered by position.

    Every language gets the universal layer (digits, English direction words); kn, en, hi and bn
    also get native number words and trigger words. Raises ValueError for an unsupported language
    or text over `MAX_TEXT_CHARS`.
    """
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language: {language!r}")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"text longer than {MAX_TEXT_CHARS} characters")
    lex = lexicon_for(language)
    tokens = tokenize(text)
    facts, used = _structured(tokens, lex, text)
    facts += _landmarks(tokens, lex, used, text)
    return sorted(facts, key=lambda fact: fact.start)
