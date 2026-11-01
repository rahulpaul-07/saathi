"""The English extractor as it was before 2026-11-01, for scoring old outputs side by side.

Before that date the English layer did not treat the full stop in "Gate No. 2" as part of the
phrase and did not know "floors". Evaluation scripts use this to score the same stored text with the
old and the new extractor, so a change in a number can be attributed to the scorer and not to the
translations. Evaluation only; the app never imports this.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from saathi.facts import lexicons, text

_ADDED_TRIGGERS = ("floors", "storeys")


@contextmanager
def legacy_english() -> Iterator[None]:
    saved_abbreviations = text._ABBREVIATIONS
    triggers = lexicons.EN.triggers
    assert isinstance(triggers, dict)
    saved = {word: triggers.pop(text.key(word)) for word in _ADDED_TRIGGERS}
    text._ABBREVIATIONS = frozenset()
    try:
        yield
    finally:
        text._ABBREVIATIONS = saved_abbreviations
        triggers.update(saved)
