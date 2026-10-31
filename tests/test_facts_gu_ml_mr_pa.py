"""Gujarati, Malayalam, Marathi and Punjabi lexicon entries, one test per entry.

Every word below is a spelling the real Gnani STT wrote (docs/LEXICON_EVIDENCE.md). They are
machine-verified, not native-reviewed. The transcripts at the end are the STT output, verbatim.
"""

import pytest

from saathi.facts import extract_facts
from saathi.facts.lexicon import Lexicon
from saathi.facts.lexicons import lexicon_for
from saathi.facts.lexicons_gu_ml_mr_pa import GU, ML, MR, PA, REVIEW_STATUS

_BLOCKS = {
    "gu": (0x0A80, 0x0AFF),
    "ml": (0x0D00, 0x0D7F),
    "mr": (0x0900, 0x097F),
    "pa": (0x0A00, 0x0A7F),
}
_LEXICONS = {"gu": GU, "ml": ML, "mr": MR, "pa": PA}

# language -> (gate, cross, filler, landmark name)
_WORDS = {
    "gu": ("ગેટ", "ક્રોસ", "નંબર", "બેકરી"),
    "ml": ("ഗേറ്റ്", "ക്രോസ്", "നമ്പർ", "ബേക്കറി"),
    "mr": ("गेट", "क्रॉस", "नंबर", "बेकरी"),
    "pa": ("ਗੇਟ", "ਕਰਾਸ", "ਨੰਬਰ", "ਬੇਕਰੀ"),
}

_CARDINALS = {
    "gu": "એક બે ત્રણ ચાર પાંચ છ સાત આઠ નવ દસ અગિયાર બાર તેર ચૌદ પંદર સોળ સત્તર અઢાર ઓગણીસ વીસ",
    "ml": (
        "ഒന്ന് രണ്ട് മൂന്ന് നാല് അഞ്ച് ആറ് ഏഴ് എട്ട് ഒമ്പത് പത്ത് പതിനൊന്ന് പന്ത്രണ്ട് പതിമൂന്ന് "
        "പതിനാല് പതിനഞ്ച് പതിനാറ് പതിനേഴ് പതിനെട്ട് പത്തൊൻപത് ഇരുപത്"
    ),
    "mr": (
        "एक दोन तीन चार पाच सहा सात आठ नऊ दहा अकरा बारा तेरा चौदा पंधरा सोळा सतरा अठरा "
        "एकोणीस वीस"
    ),
    "pa": (
        "ਇੱਕ ਦੋ ਤਿੰਨ ਚਾਰ ਪੰਜ ਛੇ ਸੱਤ ਅੱਠ ਨੌ ਦਸ ਗਿਆਰਾਂ ਬਾਰਾਂ ਤੇਰਾਂ ਚੌਦ੍ਹਾਂ ਪੰਦਰਾਂ ਸੋਲ੍ਹਾਂ ਸਤਾਰਾਂ "
        "ਅਠਾਰ੍ਹਾਂ ਉੱਨੀ ਵੀਹ"
    ),
}
_ORDINALS: dict[str, dict[int, str]] = {
    "gu": dict(enumerate(
        "પહેલો બીજો ત્રીજો ચોથો પાંચમો છઠ્ઠો સાતમો આઠમો નવમો દસમો અગિયારમો બારમો તેરમો ચૌદમો "
        "પંદરમો સોળમો સત્તરમો અઢારમો ઓગણીસમો વીસમો".split(), start=1)),
    "ml": dict(enumerate(
        "ഒന്നാം രണ്ടാം മൂന്നാം നാലാം അഞ്ചാം ആറാം ഏഴാം എട്ടാം ഒൻപതാം പത്താം പതിനൊന്നാം "
        "പന്ത്രണ്ടാം പതിമൂന്നാം പതിനാലാം പതിനഞ്ചാം പതിനാറാം പതിനേഴാം പതിനെട്ടാം പത്തൊൻപതാം "
        "ഇരുപതാം".split(), start=1)),
    "mr": dict(enumerate(
        "पहिला दुसरा तिसरा चौथा पाचवा सहावा सातवा आठवा नववा दहावा अकरावं बारावा तेरावा चौदावा "
        "पंधरावा सोळावा सतरावा अठरावा एकोणीसावा विसावा".split(), start=1)),
    # no 17: the STT wrote the spoken ordinal as the cardinal ਸਤਾਰ੍ਹਾਂ (pa-probe-8)
    "pa": {
        1: "ਪਹਿਲਾ", 2: "ਦੂਜਾ", 3: "ਤੀਜਾ", 4: "ਚੌਥਾ", 5: "ਪੰਜਵਾਂ", 6: "ਛੇਵਾਂ", 7: "ਸੱਤਵਾਂ",
        8: "ਅੱਠਵਾਂ", 9: "ਨੌਵਾਂ", 10: "ਦਸਵਾਂ", 11: "ਗਿਆਰ੍ਹਵਾਂ", 12: "ਬਾਰ੍ਹਵਾਂ", 13: "ਤੇਰ੍ਹਵਾਂ",
        14: "ਚੌਦ੍ਹਵਾਂ", 15: "ਪੰਦਰਾਂਵਾਂ", 16: "ਸੋਲਵਾਂ", 18: "ਅਠਾਰ੍ਹਵਾਂ", 19: "ਉੱਨੀਵਾਂ",
        20: "ਵੀਹਵਾਂ",
    },
}  # fmt: skip

_CARDINAL_CASES = [
    (lang, value, word)
    for lang, spec in _CARDINALS.items()
    for value, word in enumerate(spec.split(), start=1)
]
_ORDINAL_CASES = [
    (lang, value, word) for lang, table in _ORDINALS.items() for value, word in table.items()
]


def _entries(lex: Lexicon) -> list[str]:
    """Every word and phrase the lexicon matches on."""
    found = [*lex.numbers, *lex.ordinals, *lex.fillers, *lex.triggers]
    found += [" ".join(phrase) for phrase in lex.landmark_before | lex.landmark_after]
    return found


def pairs(text: str, lang: str) -> list[tuple[str, str]]:
    return [(fact.kind, fact.value) for fact in extract_facts(text, lang)]


@pytest.mark.parametrize("lang", _LEXICONS)
def test_every_entry_uses_only_its_own_script(lang: str) -> None:
    low, high = _BLOCKS[lang]
    entries = _entries(_LEXICONS[lang])
    assert entries
    stray = {
        entry: sorted({f"U+{ord(c):04X}" for c in entry if c != " " and not low <= ord(c) <= high})
        for entry in entries
    }
    assert {entry: bad for entry, bad in stray.items() if bad} == {}


@pytest.mark.parametrize(("lang", "value", "word"), _CARDINAL_CASES)
def test_each_cardinal_is_read_after_a_gate(lang: str, value: int, word: str) -> None:
    gate, _cross, filler, _name = _WORDS[lang]
    assert pairs(f"{gate} {filler} {word}", lang) == [("gate", str(value))]


@pytest.mark.parametrize(("lang", "value", "word"), _ORDINAL_CASES)
def test_each_ordinal_is_read_before_a_cross(lang: str, value: int, word: str) -> None:
    _gate, cross, _filler, _name = _WORDS[lang]
    assert pairs(f"{word} {cross}", lang) == [("cross", str(value))]


_THREE = {"gu": "ત્રીજો", "ml": "മൂന്നാം", "mr": "तिसरा", "pa": "ਤੀਜਾ"}
_FILLER_THREE = {"gu": "નંબર ત્રણ", "ml": "നമ്പർ മൂന്ന്", "mr": "नंबर तीन", "pa": "ਨੰਬਰ ਤਿੰਨ"}


@pytest.mark.parametrize(
    ("lang", "word", "kind"),
    [
        ("gu", "ગેટ", "gate"), ("gu", "ફ્લૅટ", "flat"), ("gu", "ફ્લેટ", "flat"),
        ("gu", "બ્લોક", "block"), ("gu", "ક્રોસ", "cross"), ("gu", "મેઇન", "main"),
        ("gu", "ફ્લોર", "floor"),
        ("ml", "ഗേറ്റ്", "gate"), ("ml", "ഫ്ലാറ്റ്", "flat"), ("ml", "ബ്ലോക്ക്", "block"),
        ("ml", "ക്രോസ്", "cross"), ("ml", "മെയിൻ", "main"), ("ml", "ഫ്ലോർ", "floor"),
        ("mr", "गेट", "gate"), ("mr", "फ्लॅट", "flat"), ("mr", "ब्लॉक", "block"),
        ("mr", "क्रॉस", "cross"), ("mr", "मेन", "main"), ("mr", "फ्लोअर", "floor"),
        ("pa", "ਗੇਟ", "gate"), ("pa", "ਫਲੈਟ", "flat"), ("pa", "ਬਲਾਕ", "block"),
        ("pa", "ਕਰਾਸ", "cross"), ("pa", "ਕ੍ਰਾਸ", "cross"), ("pa", "ਮੇਨ", "main"),
        ("pa", "ਫਲੋਰ", "floor"),
    ],
)  # fmt: skip
def test_each_trigger_word_gives_its_kind(lang: str, word: str, kind: str) -> None:
    text = (
        f"{word} {_FILLER_THREE[lang]}"
        if kind in {"gate", "flat", "block"}
        else f"{_THREE[lang]} {word}"
    )
    assert pairs(text, lang) == [(kind, "3")]


@pytest.mark.parametrize(
    ("lang", "cue"),
    [
        ("gu", "સામે"), ("gu", "પાસે"), ("gu", "બાજુમાં"), ("gu", "પાછળ"),
        ("ml", "എതിർവശം"), ("ml", "സമീപം"), ("ml", "അടുത്ത്"), ("ml", "പിന്നിൽ"),
        ("pa", "ਸਾਹਮਣੇ"), ("pa", "ਨੇੜੇ"), ("pa", "ਕੋਲ"), ("pa", "ਪਿੱਛੇ"),
    ],
)  # fmt: skip
def test_each_landmark_cue_makes_the_word_before_it_a_landmark(lang: str, cue: str) -> None:
    name = _WORDS[lang][3]
    assert pairs(f"{name} {cue}", lang) == [("landmark", name)]


def test_marathi_has_no_landmark_cues_because_the_stt_glued_them_to_the_name() -> None:
    assert MR.landmark_after == frozenset()
    assert pairs("बेकरीसमोर", "mr") == []


def test_punjabi_cardinal_before_a_trigger_is_read_as_the_ordinal_the_stt_wrote() -> None:
    # pa-probe-8: the spoken ordinal 17 was written as the cardinal ਸਤਾਰ੍ਹਾਂ.
    assert pairs("ਸਤਾਰ੍ਹਾਂ ਕ੍ਰਾਸ", "pa") == [("cross", "17")]


def test_words_the_stt_did_not_write_and_noise_give_no_chip() -> None:
    assert pairs("ગેટ નંબર એકવીસ", "gu") == []  # above 20: not probed
    assert pairs("ഗേറ്റ് നമ്പർ", "ml") == []  # a trigger with no value
    assert pairs("पंधरावा मीन", "mr") == []
    assert pairs("ਪੰਦਰਾਂਵਾਂ ਮੀਨ", "pa") == []


def test_the_new_languages_are_registered_with_their_native_layer() -> None:
    for lang, lex in _LEXICONS.items():
        assert set(lex.numbers) <= set(lexicon_for(lang).numbers)
        assert lexicon_for(lang).triggers.keys() >= lex.triggers.keys()


def test_the_review_status_is_stated_in_code() -> None:
    assert REVIEW_STATUS == "machine-verified, not native-reviewed"


# --- Real STT transcripts, verbatim (synthetic sentences, no address) ---------------------------

GU_FLOORS = "છઠ્ઠો ફ્લોર સાતમો ફ્લોર આઠમો ફ્લોર નવમો ફ્લોર દસમો ફ્લોર બેકરી પાસે"
ML_GATES = "ഗേറ്റ് നമ്പർ ഒന്ന് ഗേറ്റ് നമ്പർ രണ്ട് ഗേറ്റ് നമ്പർ മൂന്ന് ഗേറ്റ് നമ്പർ നാല് ഗേറ്റ് നമ്പർ അഞ്ച്"
MR_BLOCKS = "ब्लॉक नंबर सोळा ब्लॉक नंबर सतरा ब्लॉक नंबर अठरा ब्लॉक नंबर एकोणीस ब्लॉक नंबर वीस"
PA_CROSSES = "ਸੋਲਵਾਂ ਕ੍ਰਾਸ ਸਤਾਰ੍ਹਾਂ ਕ੍ਰਾਸ ਅਠਾਰ੍ਹਵਾਂ ਕਰਾਸ ਉੱਨੀਵਾਂ ਕ੍ਰਾਸ ਵੀਹਵਾਂ ਕ੍ਰਾਸ ਬੇਕਰੀ ਪਿੱਛੇ"


def test_a_gujarati_transcript_of_ordinal_floors_gives_floors_and_the_landmark() -> None:
    assert pairs(GU_FLOORS, "gu") == [("floor", str(n)) for n in range(6, 11)] + [
        ("landmark", "બેકરી")
    ]


def test_a_malayalam_transcript_with_five_gates_gives_five_gate_chips() -> None:
    assert pairs(ML_GATES, "ml") == [("gate", str(n)) for n in range(1, 6)]


def test_a_marathi_transcript_of_blocks_gives_blocks_16_to_20() -> None:
    assert pairs(MR_BLOCKS, "mr") == [("block", str(n)) for n in range(16, 21)]


def test_a_punjabi_transcript_of_crosses_gives_crosses_and_the_landmark() -> None:
    assert pairs(PA_CROSSES, "pa") == [("cross", str(n)) for n in range(16, 21)] + [
        ("landmark", "ਬੇਕਰੀ")
    ]
