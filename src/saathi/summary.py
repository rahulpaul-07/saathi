"""The templated fact summary spoken when a masked translation cannot be trusted.

Built only from the extracted facts and the loanword table, so it needs no sentence grammar in any
language: "2 ಕ್ರಾಸ್, 3 ಮೇನ್, ಗೇಟ್ 2". The order of value and word follows what the extractor reads
back ("2nd cross", "gate 2"), so the summary survives a round trip through `extract_facts`.
"""

from collections.abc import Sequence

from saathi.facts import Fact
from saathi.loanwords import written

# Kinds spoken as "2 cross"; the rest as "gate 2".
_VALUE_FIRST = frozenset({"cross", "main", "floor"})


def _spoken_value(fact: Fact) -> str:
    # An ambiguous reading stays digit by digit ("1 4"), as the speaker said it.
    return " ".join(fact.reading) if fact.ambiguous and fact.reading else fact.value


def fact_summary(facts: Sequence[Fact], tgt: str) -> str:
    """The facts in `tgt`, in speaking order. A landmark appears only if it has a `local` name."""
    parts: list[str] = []
    for fact in sorted(facts, key=lambda item: item.start):
        if fact.kind == "landmark":
            if fact.local:
                parts.append(f"{written('landmark', tgt)} {fact.local}")
            continue
        word, value = written(fact.kind, tgt), _spoken_value(fact)
        parts.append(f"{value} {word}" if fact.kind in _VALUE_FIRST else f"{word} {value}")
    return ", ".join(parts)
