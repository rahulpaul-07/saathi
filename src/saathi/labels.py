"""Chip labels (GATE, CROSS, MAIN, FLOOR, FLAT, BLOCK, LANDMARK) in each person's own language.

The default spelling of a label is the loanword spelling people actually use in that language
(`saathi.loanwords`): in bn "গেট", "ক্রস", "মেইন". Where an author-reviewed quick reply already
uses a word for the same thing, that word wins and the label is `reviewed`: bn "তলা" for floor
("কত তলায়?"), hi "फ्लोर" ("कौन सा फ्लोर?"), and the gate in both. Everything else is an unreviewed
machine or hand-written spelling and is marked `pending`, so the UI can say so.
"""

from dataclasses import dataclass
from typing import Literal

from saathi.languages import LANGUAGES
from saathi.loanwords import written

LabelStatus = Literal["source", "reviewed", "pending"]

KINDS: tuple[str, ...] = ("gate", "floor", "cross", "main", "block", "flat", "landmark")

# (kind, language) -> spelling taken from a reviewed quick reply, over the loanword default.
_REVIEWED: dict[tuple[str, str], str] = {
    ("gate", "bn"): "গেট",  # "আমি গেটে আছি"
    ("floor", "bn"): "তলা",  # "কত তলায়?"
    ("gate", "hi"): "गेट",  # "मैं गेट पर हूँ"
    ("floor", "hi"): "फ्लोर",  # "कौन सा फ्लोर?"
}


@dataclass(frozen=True)
class Label:
    text: str
    status: LabelStatus


def chip_label(kind: str, language: str) -> Label:
    """The label of a fact class in `language`; KeyError for an unknown kind or language."""
    if language not in LANGUAGES:
        raise KeyError(language)
    if language == "en":
        return Label(written(kind, "en").capitalize(), "source")
    reviewed = _REVIEWED.get((kind, language))
    if reviewed is not None:
        return Label(reviewed, "reviewed")
    return Label(written(kind, language), "pending")
