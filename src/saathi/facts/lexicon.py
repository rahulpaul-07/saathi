"""The shape of a language's extraction data, and helpers that build it in normalized form."""

from collections.abc import Mapping
from dataclasses import dataclass

from saathi.facts.text import key
from saathi.facts.types import FactKind


@dataclass(frozen=True)
class Lexicon:
    """Everything the extractor knows about one language; all keys are `key()`-normalized."""

    numbers: Mapping[str, int]  # single-token cardinals, hundreds included ("ಮುನ್ನೂರ" = 300)
    ordinals: Mapping[str, int]  # single-token ordinal words ("third", "ಮೂರನೇ", "तीसरा")
    hundred_words: frozenset[str]  # "hundred", "सौ": multiplies a preceding 1-9
    hundred_joiners: frozenset[str]  # "and" in "two hundred and four"
    spaced_tens: bool  # tens and units are separate tokens ("twenty one")
    ordinal_suffix_tokens: frozenset[str]  # split ordinal marker after a number ("ಎರಡು ನೇ")
    digit_ordinal_suffixes: frozenset[str]  # glued to digits ("2nd", "2য")
    fillers: frozenset[str]  # "number", "नंबर" between a trigger and its value
    letters: Mapping[str, str]  # spoken letter names ("ಬಿ" -> "B") for tower and flat labels
    triggers: Mapping[str, FactKind]  # structural trigger word -> fact kind
    landmark_before: frozenset[tuple[str, ...]]  # trigger precedes the name ("opposite X")
    landmark_after: frozenset[tuple[str, ...]]  # postposition follows the name ("X के सामने")
    stopwords: frozenset[str]  # end a landmark name ("my house", "turn left")
    leading_particles: frozenset[str]  # dropped from the start of a landmark ("the")
    trailing_particles: frozenset[str]  # dropped from its end (Hindi "के")


def words(spec: str) -> frozenset[str]:
    return frozenset(key(word) for word in spec.split())


def phrases(spec: str) -> frozenset[tuple[str, ...]]:
    """`|`-separated phrases, each a run of words: "next to|in front of"."""
    return frozenset(tuple(key(word) for word in item.split()) for item in spec.split("|"))


def table(spec: str, start: int = 0) -> dict[str, int]:
    """Consecutive numbers from `start` for a space-separated list of words."""
    return {key(word): start + offset for offset, word in enumerate(spec.split())}


def same(spec: str, value: int) -> dict[str, int]:
    """Spelling or gender variants of one number: "दूसरा दूसरी दूसरे" all mean 2."""
    return {key(word): value for word in spec.split()}


def trigger_map(
    *, gate: str, floor: str, cross: str, main: str, block: str, flat: str
) -> dict[str, FactKind]:
    """Structural trigger words per kind (landmarks have their own phrase sets)."""
    by_kind: dict[FactKind, str] = {
        "gate": gate,
        "floor": floor,
        "cross": cross,
        "main": main,
        "block": block,
        "flat": flat,
    }
    return {key(word): kind for kind, spec in by_kind.items() for word in spec.split()}


def merge(*lexicons: Lexicon) -> Lexicon:
    """Union of lexicons: the universal English layer plus a native layer."""
    numbers: dict[str, int] = {}
    ordinals: dict[str, int] = {}
    letters: dict[str, str] = {}
    structural: dict[str, FactKind] = {}
    for lexicon in lexicons:
        numbers |= lexicon.numbers
        ordinals |= lexicon.ordinals
        letters |= lexicon.letters
        structural |= lexicon.triggers
    return Lexicon(
        numbers=numbers,
        ordinals=ordinals,
        hundred_words=frozenset().union(*(lx.hundred_words for lx in lexicons)),
        hundred_joiners=frozenset().union(*(lx.hundred_joiners for lx in lexicons)),
        spaced_tens=any(lx.spaced_tens for lx in lexicons),
        ordinal_suffix_tokens=frozenset().union(*(lx.ordinal_suffix_tokens for lx in lexicons)),
        digit_ordinal_suffixes=frozenset().union(*(lx.digit_ordinal_suffixes for lx in lexicons)),
        fillers=frozenset().union(*(lx.fillers for lx in lexicons)),
        letters=letters,
        triggers=structural,
        landmark_before=frozenset().union(*(lx.landmark_before for lx in lexicons)),
        landmark_after=frozenset().union(*(lx.landmark_after for lx in lexicons)),
        stopwords=frozenset().union(*(lx.stopwords for lx in lexicons)),
        leading_particles=frozenset().union(*(lx.leading_particles for lx in lexicons)),
        trailing_particles=frozenset().union(*(lx.trailing_particles for lx in lexicons)),
    )
