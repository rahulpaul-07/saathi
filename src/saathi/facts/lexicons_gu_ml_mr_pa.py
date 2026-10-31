"""Gujarati, Malayalam, Marathi and Punjabi extraction data, built from what Gnani STT wrote.

Status of every entry: machine-verified, not native-reviewed. Each spelling below was produced by
the real STT in `scripts/probe_numbers.py --round2` (TTS of a probe sentence, then STT); the
evidence per entry is in docs/LEXICON_EVIDENCE.md and the sentences are in
`saathi.evaluation.lexprobe`. A word the STT never wrote is absent even when it is standard in the
language, so a gap means "not heard", not "wrong". Numbers stop at 20, which is what was probed;
above 20 only digits are understood.

The STT wrote number words, never digits, for all four languages: without this table a spoken gate,
cross or floor produces no chip at all.

Marathi landmarks are not covered: the STT glued the cue to the name ("बेकरीसमोर"), and the
extractor matches whole tokens, so there is no postposition to recognise.
"""

from collections.abc import Mapping

from saathi.facts.lexicon import Lexicon, phrases, same, trigger_map, words
from saathi.facts.lexicons_ta_te import REVIEW_STATUS
from saathi.facts.types import FactKind

__all__ = ["GU", "ML", "MR", "PA", "REVIEW_STATUS"]


def _forms(spellings: dict[int, str]) -> dict[str, int]:
    """{value: "spelling another-spelling"} -> {normalized word: value}."""
    merged: dict[str, int] = {}
    for value, spec in spellings.items():
        merged |= same(spec, value)
    return merged


def _numbered(spec: str) -> dict[int, str]:
    """The twenty space-separated words of `spec` as the values 1 to 20."""
    return dict(enumerate(spec.split(), start=1))


def _lexicon(
    *,
    cardinals: dict[int, str],
    ordinals: dict[int, str],
    fillers: str,
    triggers: Mapping[str, FactKind],
    landmark_after: str,
) -> Lexicon:
    return Lexicon(
        numbers=_forms(cardinals),
        ordinals=_forms(ordinals),
        hundred_words=frozenset(),
        hundred_joiners=frozenset(),
        spaced_tens=False,
        ordinal_suffix_tokens=frozenset(),
        digit_ordinal_suffixes=frozenset(),
        fillers=words(fillers),
        letters={},
        triggers=triggers,
        landmark_before=frozenset(),
        landmark_after=phrases(landmark_after) if landmark_after else frozenset(),
        stopwords=frozenset(),
        leading_particles=frozenset(),
        trailing_particles=frozenset(),
    )


# --- Gujarati ---------------------------------------------------------------------------------

# Every number word was written exactly as it was spoken (gu-probe-1..8). The STT wrote "flat"
# two ways (gu-probe-2) and "main" as મેઇન for the spoken મેઈન.
GU = _lexicon(
    cardinals=_numbered(
        "એક બે ત્રણ ચાર પાંચ છ સાત આઠ નવ દસ અગિયાર બાર તેર ચૌદ પંદર સોળ સત્તર અઢાર ઓગણીસ વીસ"
    ),
    ordinals=_numbered(
        "પહેલો બીજો ત્રીજો ચોથો પાંચમો છઠ્ઠો સાતમો આઠમો નવમો દસમો અગિયારમો બારમો તેરમો ચૌદમો "
        "પંદરમો સોળમો સત્તરમો અઢારમો ઓગણીસમો વીસમો"
    ),
    fillers="નંબર",
    triggers=trigger_map(
        gate="ગેટ",
        floor="ફ્લોર",
        cross="ક્રોસ",
        main="મેઇન",
        block="બ્લોક",
        flat="ફ્લૅટ ફ્લેટ",
    ),
    landmark_after="સામે|પાસે|બાજુમાં|પાછળ",
)

# --- Malayalam --------------------------------------------------------------------------------

# 9 was written ഒമ്പത് as a cardinal and ഒൻപതാം as an ordinal; 19 was written പത്തൊൻപത്, not the
# spoken പത്തൊമ്പത്. "മെയിൻ" came back as "മീൻ" (fish) once, for 15 (ml-probe-7): not mapped.
ML = _lexicon(
    cardinals={
        1: "ഒന്ന്", 2: "രണ്ട്", 3: "മൂന്ന്", 4: "നാല്", 5: "അഞ്ച്",
        6: "ആറ്", 7: "ഏഴ്", 8: "എട്ട്", 9: "ഒമ്പത്", 10: "പത്ത്",
        11: "പതിനൊന്ന്", 12: "പന്ത്രണ്ട്", 13: "പതിമൂന്ന്", 14: "പതിനാല്", 15: "പതിനഞ്ച്",
        16: "പതിനാറ്", 17: "പതിനേഴ്", 18: "പതിനെട്ട്", 19: "പത്തൊൻപത്", 20: "ഇരുപത്",
    },  # fmt: skip
    ordinals={
        1: "ഒന്നാം", 2: "രണ്ടാം", 3: "മൂന്നാം", 4: "നാലാം", 5: "അഞ്ചാം",
        6: "ആറാം", 7: "ഏഴാം", 8: "എട്ടാം", 9: "ഒൻപതാം ഒമ്പതാം", 10: "പത്താം",
        11: "പതിനൊന്നാം", 12: "പന്ത്രണ്ടാം", 13: "പതിമൂന്നാം", 14: "പതിനാലാം", 15: "പതിനഞ്ചാം",
        16: "പതിനാറാം", 17: "പതിനേഴാം", 18: "പതിനെട്ടാം", 19: "പത്തൊൻപതാം", 20: "ഇരുപതാം",
    },  # fmt: skip
    fillers="നമ്പർ",
    triggers=trigger_map(
        gate="ഗേറ്റ്",
        floor="ഫ്ലോർ",
        cross="ക്രോസ്",
        main="മെയിൻ",
        block="ബ്ലോക്ക്",
        flat="ഫ്ലാറ്റ്",
    ),
    landmark_after="എതിർവശം|സമീപം|അടുത്ത്|പിന്നിൽ",
)

# --- Marathi ----------------------------------------------------------------------------------

# 11 as an ordinal was written अकरावं (mr-probe-7), not the spoken अकरावा; 19 as an ordinal was
# written एकोणीसावा, not the spoken एकोणिसावा.
MR = _lexicon(
    cardinals=_numbered(
        "एक दोन तीन चार पाच सहा सात आठ नऊ दहा अकरा बारा तेरा चौदा पंधरा सोळा सतरा अठरा एकोणीस वीस"
    ),
    ordinals={
        1: "पहिला", 2: "दुसरा", 3: "तिसरा", 4: "चौथा", 5: "पाचवा",
        6: "सहावा", 7: "सातवा", 8: "आठवा", 9: "नववा", 10: "दहावा",
        11: "अकरावं", 12: "बारावा", 13: "तेरावा", 14: "चौदावा", 15: "पंधरावा",
        16: "सोळावा", 17: "सतरावा", 18: "अठरावा", 19: "एकोणीसावा", 20: "विसावा",
    },  # fmt: skip
    fillers="नंबर",
    triggers=trigger_map(
        gate="गेट",
        floor="फ्लोअर",
        cross="क्रॉस",
        main="मेन",
        block="ब्लॉक",
        flat="फ्लॅट",
    ),
    landmark_after="",
)

# --- Punjabi ----------------------------------------------------------------------------------

# Written differently from the speech: 9 ਨੌ (spoken ਨੌਂ), 14 ਚੌਦ੍ਹਾਂ, 16 ਸੋਲ੍ਹਾਂ, 18 ਅਠਾਰ੍ਹਾਂ and the
# ordinals 11-14 with a half-h (ਗਿਆਰ੍ਹਵਾਂ). 15 as an ordinal was ਪੰਦਰਾਂਵਾਂ. The STT wrote the
# spoken ordinal 17 as the cardinal ਸਤਾਰ੍ਹਾਂ, so 17 has no ordinal entry; as a cardinal before a
# trigger it already reads as 17. "ਕਰਾਸ" and "ਕ੍ਰਾਸ" were both written for "cross".
PA = _lexicon(
    cardinals={
        1: "ਇੱਕ", 2: "ਦੋ", 3: "ਤਿੰਨ", 4: "ਚਾਰ", 5: "ਪੰਜ",
        6: "ਛੇ", 7: "ਸੱਤ", 8: "ਅੱਠ", 9: "ਨੌ", 10: "ਦਸ",
        11: "ਗਿਆਰਾਂ", 12: "ਬਾਰਾਂ ਬਾਰ੍ਹਾਂ", 13: "ਤੇਰਾਂ", 14: "ਚੌਦ੍ਹਾਂ", 15: "ਪੰਦਰਾਂ",
        16: "ਸੋਲ੍ਹਾਂ", 17: "ਸਤਾਰਾਂ ਸਤਾਰ੍ਹਾਂ", 18: "ਅਠਾਰ੍ਹਾਂ", 19: "ਉੱਨੀ", 20: "ਵੀਹ",
    },  # fmt: skip
    ordinals={
        1: "ਪਹਿਲਾ", 2: "ਦੂਜਾ", 3: "ਤੀਜਾ", 4: "ਚੌਥਾ", 5: "ਪੰਜਵਾਂ",
        6: "ਛੇਵਾਂ", 7: "ਸੱਤਵਾਂ", 8: "ਅੱਠਵਾਂ", 9: "ਨੌਵਾਂ", 10: "ਦਸਵਾਂ",
        11: "ਗਿਆਰ੍ਹਵਾਂ", 12: "ਬਾਰ੍ਹਵਾਂ", 13: "ਤੇਰ੍ਹਵਾਂ", 14: "ਚੌਦ੍ਹਵਾਂ", 15: "ਪੰਦਰਾਂਵਾਂ",
        16: "ਸੋਲਵਾਂ", 18: "ਅਠਾਰ੍ਹਵਾਂ", 19: "ਉੱਨੀਵਾਂ", 20: "ਵੀਹਵਾਂ",
    },  # fmt: skip
    fillers="ਨੰਬਰ",
    triggers=trigger_map(
        gate="ਗੇਟ",
        floor="ਫਲੋਰ",
        cross="ਕਰਾਸ ਕ੍ਰਾਸ",
        main="ਮੇਨ",
        block="ਬਲਾਕ",
        flat="ਫਲੈਟ",
    ),
    landmark_after="ਸਾਹਮਣੇ|ਨੇੜੇ|ਕੋਲ|ਪਿੱਛੇ",
)
