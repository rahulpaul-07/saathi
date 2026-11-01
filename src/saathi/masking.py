"""Placeholder masking: keep numbers and address loanwords out of the translation model's hands.

A translation model turns "opposite" into "related", "main" into "principal" and a bare "2" into
a different number word or none at all. So before translating, the value of each number fact and
each loanword (`saathi.loanwords`) is replaced by a numbered placeholder; after translating, the
placeholders are replaced by the digits and by the loanword spelled in the listener's script.

A translation is `verified` only when every placeholder came back exactly once and nothing else
looks like one. Anything else means the model dropped, duplicated or invented a slot, and the
caller must not speak that text (it speaks a fact summary instead, `saathi.summary`).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Literal

from saathi.facts import Fact, extract_facts
from saathi.facts.lexicons import EN, NATIVE
from saathi.facts.text import ascii_digits, tokenize
from saathi.languages import LANGUAGES
from saathi.loanwords import concept_of, written
from saathi.translate import Translator

# Probed in scripts/probe_placeholders.py (eval/results/placeholder_probe.json): 29 of 30 dev
# translations returned every slot once, against 12 of 30 for "<ID{n}>". The toolkit wraps a
# "#word" token in its own <IDn> entity before the model sees it and unwraps it afterwards, which
# is the form the model was trained to copy. {n} is a slot number.
PLACEHOLDER_TEMPLATE = "#L{n}"
# Slots count up from here so they never equal a number the toolkit's own entity wrapping uses.
FIRST_SLOT = 51

MaskingMode = Literal["current", "conditional"]
# The values a listener hears as an ordinal ("second cross", "fourth floor"). Restoring a bare
# digit turned "fourth floor" into "4 floors" for the back-translation (docs/EVAL.md).
ORDINAL_KINDS = frozenset({"floor", "cross", "main"})
# Ordinal words come from the lexicon, whose spellings are normalized (`facts.text.key`). Bengali
# loses its nukta that way (দ্বিতীয় becomes দ্বিতীয), so Bengali is left out and keeps its value
# unmasked instead of being restored in a wrong spelling.
ORDINAL_RESTORE_LANGUAGES = frozenset({"en", "hi", "kn", "gu", "ml", "mr", "pa", "ta", "te"})


@dataclass(frozen=True)
class Slot:
    number: int
    kind: Literal["loanword", "value", "ordinal"]
    text: str  # a loanword concept ("cross") or the value to restore ("2", "5B")


@dataclass(frozen=True)
class MaskedText:
    text: str
    slots: tuple[Slot, ...]


@dataclass(frozen=True)
class Restored:
    text: str
    verified: bool  # every slot returned exactly once and no unknown placeholder appeared


def _pattern(template: str) -> re.Pattern[str]:
    prefix, _, suffix = template.partition("{n}")
    # Whitespace is tolerated inside the marker only; a space after a bare marker is text.
    tail = r"\s*" + re.escape(suffix.lstrip()) if suffix.strip() else ""
    return re.compile(re.escape(prefix.rstrip()) + r"\s*(\d+)" + tail, re.IGNORECASE)


@cache
def _ordinal_words(tgt: str) -> dict[int, str]:
    """value -> the first ordinal word the `tgt` lexicon lists for it (empty if unsupported)."""
    lexicon = EN if tgt == "en" else NATIVE.get(tgt)
    if lexicon is None or tgt not in ORDINAL_RESTORE_LANGUAGES:
        return {}
    words: dict[int, str] = {}
    for word, value in lexicon.ordinals.items():
        words.setdefault(value, word)
    return words


def ordinal_word(value: str, tgt: str) -> str | None:
    """The `tgt` ordinal word for a plain number value ("2" -> "second"), or None."""
    return _ordinal_words(tgt).get(int(value)) if value.isascii() and value.isdecimal() else None


def mask(
    text: str,
    src: str,
    facts: Sequence[Fact],
    template: str = PLACEHOLDER_TEMPLATE,
    tgt: str | None = None,
    mode: MaskingMode = "current",
) -> MaskedText:
    """Replace each clear number value and each loanword in `text` (a `src` transcript).

    `facts` must come from `extract_facts(text, src)`. An ambiguous reading ("one four") is left
    alone: its digits are a guess, and a guess must not be spoken as if it were certain.

    In "conditional" mode (needs `tgt`) the value of a floor, cross or main fact is masked as an
    ordinal slot when the `tgt` lexicon has a word for it, and left in the text otherwise; gate,
    flat and block values are masked as before.
    """
    if mode == "conditional" and tgt is None:
        raise ValueError("conditional masking needs the target language")
    spans: list[tuple[int, int, Literal["loanword", "value", "ordinal"], str]] = []
    for fact in facts:
        if fact.value_start is None or fact.value_end is None or fact.ambiguous:
            continue
        if mode == "conditional" and fact.kind in ORDINAL_KINDS:
            if tgt is not None and ordinal_word(fact.value, tgt) is not None:
                spans.append((fact.value_start, fact.value_end, "ordinal", fact.value))
            continue
        spans.append((fact.value_start, fact.value_end, "value", fact.value))
    for token in tokenize(text):
        concept = concept_of(token.key, src)
        covered = any(start < token.end and token.start < end for start, end, _, _ in spans)
        if concept is not None and not covered:
            spans.append((token.start, token.end, "loanword", concept))
    spans.sort()

    pieces: list[str] = []
    slots: list[Slot] = []
    cursor = 0
    for start, end, kind, payload in spans:
        number = FIRST_SLOT + len(slots)
        slots.append(Slot(number, kind, payload))
        pieces += [text[cursor:start], template.format(n=number)]
        cursor = end
    pieces.append(text[cursor:])
    return MaskedText("".join(pieces), tuple(slots))


def restore(
    translated: str, masked: MaskedText, tgt: str, template: str = PLACEHOLDER_TEMPLATE
) -> Restored:
    """Put the digits and the `tgt`-script loanwords back where the placeholders came out."""
    by_number = {slot.number: slot for slot in masked.slots}
    seen: list[int] = []

    def put_back(match: re.Match[str]) -> str:
        number = int(match.group(1))
        seen.append(number)
        slot = by_number.get(number)
        if slot is None:
            return match.group(0)
        if slot.kind == "loanword":
            return written(slot.text, tgt)
        if slot.kind == "ordinal":
            return ordinal_word(slot.text, tgt) or slot.text
        return slot.text

    # The model may write a native digit of its own; the listener always sees and hears 0-9.
    text = ascii_digits(_pattern(template).sub(put_back, translated))
    return Restored(text, verified=sorted(seen) == sorted(by_number))


@dataclass(frozen=True)
class MaskedTranslation:
    text: str
    verified: bool
    raw: str  # what the model returned, placeholders included (evaluation only; may hold addresses)


def translate_masked(
    translator: Translator,
    text: str,
    src: str,
    tgt: str,
    facts: Sequence[Fact] | None = None,
    mode: MaskingMode = "current",
) -> MaskedTranslation:
    """Mask, translate, restore. Raises whatever the translator raises."""
    if src not in LANGUAGES:
        raise ValueError(f"unsupported language: {src!r}")
    found = extract_facts(text, src) if facts is None else facts
    masked = mask(text, src, found, tgt=tgt, mode=mode)
    raw = translator.translate(masked.text, src, tgt)
    restored = restore(raw, masked, tgt)
    return MaskedTranslation(restored.text, restored.verified, raw)
