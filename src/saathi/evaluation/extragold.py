"""Held-out synthetic gold for the six languages the main gold set (eval/gold/directions.json)
does not cover: ta, te, gu, ml, mr, pa.

The sentences recombine the words the lexicon probe already spoke (`lexprobe`), in new orders and
with number and trigger pairings the probe never used (it spoke "cross" only with 1-5 and 16-20,
"main" only with 11-15, and so on). So this tests that extraction survives composition and
pairing, NOT that new spellings are found: a word the probe did not speak is not tested.
The audio is synthetic Gnani TTS read back by Gnani STT. The set is small and has no landmark
facts: a landmark value is a free-text span, and writing its gold string needs a native reader.
"""

from saathi.evaluation.factscore import GoldFact, GoldUtterance
from saathi.evaluation.lexprobe import ProbeSentence, words_for
from saathi.facts.types import FactKind

LANGS = ("ta", "te", "gu", "ml", "mr", "pa")
LEDGER_LABEL = "facts-extra"
MAX_CALLS = 56  # 48 planned plus 8 retries; retries count against it

# Each template is (kind, ordinal?, value) items. Values avoid the probe's own pairings.
_TEMPLATES: tuple[tuple[tuple[FactKind, bool, int], ...], ...] = (
    (("cross", True, 7), ("main", True, 3), ("gate", False, 12)),
    (("block", False, 4), ("floor", True, 9), ("flat", False, 15)),
    (("gate", False, 8), ("cross", True, 13), ("main", True, 18)),
    (("floor", True, 2), ("block", False, 19), ("gate", False, 6)),
)


def _spoken(lang: str, kind: FactKind, ordinal: bool, value: int) -> str:
    words = words_for(lang)
    trigger = words.triggers[kind]
    if ordinal:
        return f"{words.ordinals[value - 1]} {trigger}"
    return f"{trigger} {words.filler} {words.cardinals[value - 1]}"


def gold_set(langs: tuple[str, ...] = LANGS) -> tuple[GoldUtterance, ...]:
    out: list[GoldUtterance] = []
    for lang in langs:
        for index, template in enumerate(_TEMPLATES, start=1):
            text = ", ".join(_spoken(lang, k, ordinal, v) for k, ordinal, v in template)
            facts = tuple(GoldFact(kind, str(value)) for kind, _, value in template)
            out.append(GoldUtterance(f"x-{lang}-{index}", "test", lang, text, facts))
    return tuple(out)


def as_probe(gold: tuple[GoldUtterance, ...]) -> tuple[ProbeSentence, ...]:
    """The TTS-then-STT runner in `lexprobe` needs only the id, language and text."""
    return tuple(ProbeSentence(g.id, g.lang, g.text, (), "") for g in gold)


def planned_calls(gold: tuple[GoldUtterance, ...]) -> int:
    return 2 * len(gold)
