"""Reads a number starting at a token: digits, number words, ordinals, hundreds, digit-by-digit.

One generic grammar driven by the lexicon, so a language is data, not a branch:

    number    := ordinal | digits[ordinal-suffix] | cardinal | digit-run
    cardinal  := [unit hundred-word | hundred-form] [joiner] [1-99]  |  1-99  |  tens unit (en)
    digit-run := two or more single digits in a row ("ಒಂದು ನಾಲ್ಕು", "1 4"): AMBIGUOUS

A digit-run is flagged because "one four" is 14 or 1 and 4 (probe: Gnani writes 14 this way).
"""

import re
from dataclasses import dataclass

from saathi.facts.lexicon import Lexicon
from saathi.facts.text import Token

_PLAIN_DIGITS = re.compile(r"\d{1,4}")
_DIGITS_WITH_TAIL = re.compile(r"(\d{1,4})(\D+)")
_DIGITS_THEN_LETTER = re.compile(r"(\d{1,4})([a-z])")
# "I" is never read as a block or flat letter: it is the English pronoun far more often.
_EXCLUDED_LATIN_LETTERS = frozenset("I")


@dataclass(frozen=True)
class Number:
    value: str  # "14", "5B"; for an ambiguous run, the joined candidate reading
    end: int  # index of the first token after the number
    ambiguous: bool = False

    @property
    def magnitude(self) -> int:
        """The numeric part ("5B" -> 5), for range checks."""
        match = re.match(r"\d+", self.value)
        return int(match.group()) if match else 0


def joined(tokens: list[Token], index: int) -> bool:
    """True when token `index` runs straight into the next one (no punctuation between)."""
    return 0 <= index < len(tokens) - 1 and not tokens[index].break_after


def _cardinal(token: Token, lex: Lexicon) -> int | None:
    if _PLAIN_DIGITS.fullmatch(token.key):
        return int(token.key)
    return lex.numbers.get(token.key)


def _word(token: Token, lex: Lexicon) -> int | None:
    """A number word below 100 (digits excluded)."""
    value = lex.numbers.get(token.key)
    return value if value is not None and value < 100 else None


def _single_digit(token: Token, lex: Lexicon) -> int | None:
    value = _cardinal(token, lex)
    is_plain_digit = _PLAIN_DIGITS.fullmatch(token.key) is not None
    if value is None or value > 9 or (is_plain_digit and len(token.key) != 1):
        return None
    return value


def _remainder(tokens: list[Token], start: int, lex: Lexicon) -> tuple[int, int] | None:
    """The 1-99 after a hundred ("... hundred [and] four"): (value, end)."""
    index = start
    if not joined(tokens, index - 1):
        return None
    if tokens[index].key in lex.hundred_joiners and joined(tokens, index):
        index += 1
    value = _word(tokens[index], lex) if index < len(tokens) else None
    if value is None or value == 0:
        return None
    if lex.spaced_tens and value >= 20 and value % 10 == 0 and joined(tokens, index):
        unit = _word(tokens[index + 1], lex)
        if unit is not None and 1 <= unit <= 9:
            return value + unit, index + 2
    return value, index + 1


def _cardinal_run(tokens: list[Token], start: int, lex: Lexicon) -> tuple[int, int] | None:
    first = _cardinal(tokens[start], lex)
    if first is None:
        return None
    if _PLAIN_DIGITS.fullmatch(tokens[start].key):
        return first, start + 1
    after = start + 1
    total = 0
    if first >= 100:  # a one-token hundred form ("ಮುನ್ನೂರ", "তিনশো") or "hundred" itself
        total = first
    elif (
        1 <= first <= 9
        and joined(tokens, start)
        and tokens[after].key in lex.hundred_words
        and lex.numbers.get(tokens[after].key) == 100
    ):
        total, after = first * 100, after + 1
    if total:
        rest = _remainder(tokens, after, lex) if after < len(tokens) else None
        return (total + rest[0], rest[1]) if rest else (total, after)
    if lex.spaced_tens and first >= 20 and first % 10 == 0 and joined(tokens, start):
        unit = _word(tokens[after], lex)
        if unit is not None and 1 <= unit <= 9:
            return first + unit, after + 1
    return first, after


def _digit_run(tokens: list[Token], start: int, lex: Lexicon) -> tuple[str, int] | None:
    digits: list[str] = []
    index = start
    while index < len(tokens) and (index == start or joined(tokens, index - 1)):
        digit = _single_digit(tokens[index], lex)
        if digit is None:
            break
        digits.append(str(digit))
        index += 1
    return ("".join(digits), index) if len(digits) >= 2 else None


def parse_letter(tokens: list[Token], index: int, lex: Lexicon) -> str | None:
    """A spoken or written letter label. A lone Latin letter must be capitalized ("Block C")."""
    token = tokens[index]
    if len(token.text) == 1 and token.text.isascii() and token.text.isalpha():
        upper = token.text.upper()
        return upper if token.text.isupper() and upper not in _EXCLUDED_LATIN_LETTERS else None
    return lex.letters.get(token.key)


def parse_number(
    tokens: list[Token], index: int, lex: Lexicon, *, allow_letter: bool = False
) -> Number | None:
    """The number starting at `index`, or None. `allow_letter` accepts labels like 5B."""
    token = tokens[index]
    attached = _DIGITS_THEN_LETTER.fullmatch(token.key)
    if attached:
        label = attached[1] + attached[2].upper()
        return Number(label, index + 1) if allow_letter else None
    with_tail = _DIGITS_WITH_TAIL.fullmatch(token.key)
    if with_tail:
        suffix_ok = with_tail[2] in lex.digit_ordinal_suffixes
        return Number(str(int(with_tail[1])), index + 1) if suffix_ok else None
    if token.key in lex.ordinals:
        return Number(str(lex.ordinals[token.key]), index + 1)

    run = _digit_run(tokens, index, lex)
    cardinal = _cardinal_run(tokens, index, lex)
    if run and (cardinal is None or run[1] > cardinal[1]):
        return Number(run[0], run[1], ambiguous=True)
    if cardinal is None:
        return None
    value, end = cardinal
    if joined(tokens, end - 1) and tokens[end].key in lex.ordinal_suffix_tokens:
        return Number(str(value), end + 1)  # split ordinal: "ಎರಡು ನೇ"
    if allow_letter and joined(tokens, end - 1):
        letter = parse_letter(tokens, end, lex)
        if letter:
            return Number(str(value) + letter, end + 1)
    return Number(str(value), end)
