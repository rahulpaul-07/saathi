"""Landmark names in the listener's language, for the rider's chips.

A landmark is open vocabulary, so it is the one fact the chips cannot take from a table. The name
is translated on its own with the same models as the sentence (DESIGN section 8, option a). A
short phrase is where these models misbehave, so the result must pass `plausible`; if it does not,
the fact keeps `local = None` and the chip shows the class only (option c). A wrong landmark is
worse than none.
"""

import dataclasses
import unicodedata
from collections.abc import Sequence

from saathi.facts import Fact
from saathi.guard import has_repeated_phrase
from saathi.languages import LANGUAGES
from saathi.masking import translate_masked
from saathi.translate import DegenerateTranslationError, TranslationInputError, Translator

MIN_SCRIPT_SHARE = 0.8  # of the letters, in the listener's script (digits and spaces excluded)
MAX_LENGTH_RATIO = 4  # translated characters per source character; a runaway is far above this

# IndicTrans2 script tag -> Unicode character-name prefix.
_SCRIPT_NAMES = {
    "Latn": "LATIN",
    "Deva": "DEVANAGARI",
    "Beng": "BENGALI",
    "Gujr": "GUJARATI",
    "Guru": "GURMUKHI",
    "Knda": "KANNADA",
    "Mlym": "MALAYALAM",
    "Taml": "TAMIL",
    "Telu": "TELUGU",
}


def _script_share(text: str, language: str) -> float:
    prefix = _SCRIPT_NAMES[LANGUAGES[language].indictrans_code.split("_")[1]]
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(unicodedata.name(ch, "").startswith(prefix) for ch in letters) / len(letters)


def plausible(translated: str, source: str, tgt: str) -> bool:
    """Is `translated` a believable rendering of the landmark `source` in language `tgt`?"""
    text = translated.strip()
    if not text or "#" in text or has_repeated_phrase(text):
        return False
    if len(text) > MAX_LENGTH_RATIO * max(len(source), 4):
        return False
    return _script_share(text, tgt) >= MIN_SCRIPT_SHARE


def localize_landmarks(
    facts: Sequence[Fact], src: str, tgt: str, translator: Translator
) -> tuple[Fact, ...]:
    """The same facts, each landmark carrying its name in `tgt` when that name is plausible."""
    localized: list[Fact] = []
    for fact in facts:
        if fact.kind == "landmark":
            try:
                result = translate_masked(translator, fact.value, src, tgt, facts=())
            except (DegenerateTranslationError, TranslationInputError):
                result = None
            if result is not None and result.verified and plausible(result.text, fact.value, tgt):
                fact = dataclasses.replace(fact, local=result.text.strip())
        localized.append(fact)
    return tuple(localized)
