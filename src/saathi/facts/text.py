"""Tokenization and the one normalization applied to both transcripts and lexicon entries."""

import re
import unicodedata
from dataclasses import dataclass

# Characters STT output and hand-written lexicons use inconsistently, folded to one form:
# zero-width joiners (ZWJ/ZWNJ), the nukta of Devanagari and Bengali, and chandrabindu -> anusvara.
_FOLD = {
    0x200B: None,
    0x200C: None,
    0x200D: None,
    0xFEFF: None,
    0x093C: None,
    0x09BC: None,
    0x0901: 0x0902,
    0x0981: 0x0982,
}
# A trailing virama (halant) is dropped so "ಕ್ರಾಸ್" and "ಕ್ರಾಸ" are the same key.
_TRAILING_VIRAMAS = "्্್"

_TOKEN = re.compile(r"[^\s,.;:!?।|\-–—\"()]+")
_BREAK_CHARS = frozenset(",.;:!?।|()\n")


def key(token: str) -> str:
    """Comparison form of a token: NFC, case-folded, folded variants, ASCII digits."""
    folded = unicodedata.normalize("NFC", token).casefold().translate(_FOLD)
    digits = "".join(str(unicodedata.digit(ch)) if ch.isdecimal() else ch for ch in folded)
    return digits.rstrip(_TRAILING_VIRAMAS)


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int
    key: str
    break_after: bool  # punctuation or a newline separates this token from the next one


def tokenize(text: str) -> list[Token]:
    matches = list(_TOKEN.finditer(text))
    tokens: list[Token] = []
    for index, match in enumerate(matches):
        if index + 1 < len(matches):
            gap = text[match.end() : matches[index + 1].start()]
            has_break = any(ch in _BREAK_CHARS for ch in gap)
        else:
            has_break = True
        word = match.group()
        tokens.append(Token(word, match.start(), match.end(), key(word), has_break))
    return tokens
