"""Tamil and Telugu lexicon entries, one test per entry.

Every word below is a spelling the real Gnani STT wrote (docs/LEXICON_EVIDENCE.md). They are
machine-verified, not native-reviewed. The transcripts at the end are the STT output, verbatim.
"""

import pytest

from saathi.facts import extract_facts
from saathi.facts.lexicon import Lexicon
from saathi.facts.lexicons_ta_te import REVIEW_STATUS, TA, TE

_BLOCKS = {"ta": (0x0B80, 0x0BFF), "te": (0x0C00, 0x0C7F)}


def _entries(lex: Lexicon) -> list[str]:
    """Every word and phrase the lexicon matches on."""
    found = [*lex.numbers, *lex.ordinals, *lex.fillers, *lex.triggers]
    found += [" ".join(phrase) for phrase in lex.landmark_before | lex.landmark_after]
    return found


@pytest.mark.parametrize(("lang", "lex"), [("ta", TA), ("te", TE)])
def test_every_entry_uses_only_its_own_script(lang: str, lex: Lexicon) -> None:
    low, high = _BLOCKS[lang]
    entries = _entries(lex)
    assert entries
    stray = {
        entry: sorted({f"U+{ord(c):04X}" for c in entry if c != " " and not low <= ord(c) <= high})
        for entry in entries
    }
    assert {entry: bad for entry, bad in stray.items() if bad} == {}


def pairs(text: str, lang: str) -> list[tuple[str, str]]:
    return [(fact.kind, fact.value) for fact in extract_facts(text, lang)]


TA_CARDINALS = [
    (1, "ஒன்று"), (2, "இரண்டு"), (3, "மூன்று"), (4, "நான்கு"), (5, "ஐந்து"), (6, "ஆறு"),
    (7, "ஏழு"), (8, "எட்டு"), (9, "ஒன்பது"), (10, "பத்து"), (11, "பதினொன்று"),
    (12, "பன்னிரெண்டு"), (13, "பதிமூன்று"), (14, "பதினான்கு"), (15, "பதினைந்து"),
    (16, "பதினாறு"), (17, "பதினேழு"), (18, "பதினெட்டு"), (19, "பத்தொன்பது"), (20, "இருபது"),
]  # fmt: skip
TA_ORDINALS = [  # 5 comes from the ta-ordinal-5 recheck; ta-probe-5 lost it
    (1, "முதல்"), (2, "இரண்டாவது"), (3, "மூன்றாவது"), (4, "நான்காவது"), (5, "ஐந்தாவது"),
    (6, "ஆறாவது"),
    (7, "ஏழாவது"), (8, "எட்டாவது"), (9, "ஒன்பதாவது"), (10, "பத்தாவது"), (11, "பதினொன்றாவது"),
    (12, "பன்னிரெண்டாவது"), (13, "பதிமூன்றாவது"), (14, "பதினான்காவது"),
    (15, "பதினைந்தாவது"), (16, "பதினாறாவது"), (17, "பதினேழாவது"), (18, "பதினெட்டாவது"),
    (19, "பத்தொன்பதாவது"), (20, "இருபதாவது"),
]  # fmt: skip
TE_CARDINALS = [
    (1, "ఒకటి"), (2, "రెండు"), (3, "మూడు"), (4, "నాలుగు"), (5, "ఐదు"), (6, "ఆరు"),
    (7, "ఏడు"), (8, "ఎనిమిది"), (9, "తొమ్మిది"), (10, "పది"), (11, "పదకొండు"),
    (12, "పన్నెండు"), (13, "పదమూడు"), (14, "పద్నాలుగు"), (15, "పదిహేను"), (16, "పదహారు"),
    (17, "పదిహేడు"), (18, "పద్దెనిమిది"), (19, "పందొమ్మిది"), (20, "ఇరవై"),
]  # fmt: skip
TE_ORDINALS = [  # no 16, 17, 19, 20: the STT wrote those as cardinals (te-probe-8)
    (1, "మొదటి"), (2, "రెండో"), (3, "మూడో"), (4, "నాలుగో"), (5, "ఐదో"), (6, "ఆరవ"),
    (7, "ఏడవ"), (8, "ఎనిమిదవ"), (9, "తొమ్మిదవ"), (10, "పదవ"), (11, "పదకొండో"),
    (12, "పన్నెండో"), (13, "పదమూడో"), (14, "పద్నాలుగో"), (15, "పదిహేనో"), (18, "పద్దెనిమిదో"),
]  # fmt: skip

# language -> (gate, cross, filler words, landmark name, cue words)
TA_WORDS = {"gate": "கேட்", "cross": "கிராஸ்", "filler": "நம்பர்", "name": "பேக்கரி"}
TE_WORDS = {"gate": "గేట్", "cross": "క్రాస్", "filler": "నంబర్", "name": "బేకరీ"}


def _cardinal_cases(lang: str, entries: list[tuple[int, str]]) -> list[tuple[str, int, str]]:
    return [(lang, value, word) for value, word in entries]


@pytest.mark.parametrize(
    ("lang", "value", "word"),
    _cardinal_cases("ta", TA_CARDINALS) + _cardinal_cases("te", TE_CARDINALS),
)
def test_each_cardinal_is_read_after_a_gate(lang: str, value: int, word: str) -> None:
    words = TA_WORDS if lang == "ta" else TE_WORDS
    assert pairs(f"{words['gate']} {words['filler']} {word}", lang) == [("gate", str(value))]


@pytest.mark.parametrize(
    ("lang", "value", "word"),
    _cardinal_cases("ta", TA_ORDINALS) + _cardinal_cases("te", TE_ORDINALS),
)
def test_each_ordinal_is_read_before_a_cross(lang: str, value: int, word: str) -> None:
    words = TA_WORDS if lang == "ta" else TE_WORDS
    assert pairs(f"{word} {words['cross']}", lang) == [("cross", str(value))]


@pytest.mark.parametrize(
    ("lang", "word", "kind"),
    [
        ("ta", "கேட்", "gate"), ("ta", "பிளாட்", "flat"), ("ta", "பிளாக்", "block"),
        ("ta", "கிராஸ்", "cross"), ("ta", "மெயின்", "main"), ("ta", "ஃப்ளோர்", "floor"),
        ("ta", "இப்ளோர்", "floor"), ("ta", "இப்லோர்", "floor"), ("ta", "இப்லோ", "floor"),
        ("te", "గేట్", "gate"), ("te", "ఫ్లాట్", "flat"), ("te", "బ్లాక్", "block"),
        ("te", "క్రాస్", "cross"), ("te", "మెయిన్", "main"), ("te", "ఫ్లోర్", "floor"),
    ],
)  # fmt: skip
def test_each_trigger_word_gives_its_kind(lang: str, word: str, kind: str) -> None:
    three = "மூன்றாவது" if lang == "ta" else "మూడో"
    filler_three = "நம்பர் மூன்று" if lang == "ta" else "నంబర్ మూడు"
    text = f"{word} {filler_three}" if kind in {"gate", "flat", "block"} else f"{three} {word}"
    assert pairs(text, lang) == [(kind, "3")]


def test_both_telugu_spellings_of_number_filler_work() -> None:
    assert pairs("గేట్ నెంబర్ ఒకటి", "te") == [("gate", "1")]
    assert pairs("గేట్ నంబర్ ఒకటి", "te") == [("gate", "1")]


@pytest.mark.parametrize(
    ("lang", "name", "cue"),
    [
        ("ta", "பேக்கரி", "எதிரில்"), ("ta", "பேக்கரி", "அருகில்"),
        ("ta", "பேக்கரி", "பக்கத்தில்"), ("ta", "பேக்கரி", "பின்னால்"),
        ("te", "బేకరీ", "ఎదురుగా"), ("te", "బేకరీ", "దగ్గర"),
        ("te", "బేకరీ", "పక్కన"), ("te", "బేకరీ", "వెనుక"),
    ],
)  # fmt: skip
def test_each_landmark_cue_makes_the_word_before_it_a_landmark(
    lang: str, name: str, cue: str
) -> None:
    assert pairs(f"{name} {cue}", lang) == [("landmark", name)]


def test_telugu_cardinal_before_a_trigger_is_read_as_the_ordinal_the_stt_wrote() -> None:
    # te-probe-8: the spoken ordinals 16 and 17 were written as cardinals.
    assert pairs("పదహారు క్రాస్ పదిహేడు క్రాస్", "te") == [("cross", "16"), ("cross", "17")]


def test_words_the_stt_did_not_write_and_noise_give_no_chip() -> None:
    assert pairs("கேட் நம்பர் இருபத்தி ஒன்று", "ta") == []  # above 20: not probed
    assert pairs("గేట్ నంబర్", "te") == []  # a trigger with no value
    assert pairs("పద్దెనిమిదో క్లాస్", "te") == []  # the STT wrote "class" for "cross" once


def test_the_review_status_is_stated_in_code() -> None:
    assert REVIEW_STATUS == "machine-verified, not native-reviewed"


# --- Real STT transcripts, verbatim (synthetic sentences, no address) ---------------------------

TA_GATE_CLIP = "இரண்டாவது கிராஸ் மூன்றாவது மெயின் கேட் நம்பர் மூன்று பேக்கரி எதிரில்"
TE_GATE_CLIP = "రెండో క్రాస్ నాలుగు మెయిన్ గేట్ నంబర్ ఒకటి హనుమాన్ గుడి ఎదురుగా"


def test_the_ta_gate_demo_clip_transcript_gives_every_intended_chip() -> None:
    assert pairs(TA_GATE_CLIP, "ta") == [
        ("cross", "2"), ("main", "3"), ("gate", "3"), ("landmark", "பேக்கரி")
    ]  # fmt: skip


def test_the_te_gate_demo_clip_transcript_gives_every_intended_chip() -> None:
    assert pairs(TE_GATE_CLIP, "te") == [
        ("cross", "2"), ("main", "4"), ("gate", "1"), ("landmark", "హనుమాన్ గుడి")
    ]  # fmt: skip


def test_a_probe_transcript_with_five_gates_gives_five_gate_chips() -> None:
    heard = "கேட் நம்பர் ஒன்று கேட் நம்பர் இரண்டு கேட் நம்பர் மூன்று கேட் நம்பர் நான்கு கேட் நம்பர் ஐந்து"
    assert pairs(heard, "ta") == [("gate", str(n)) for n in range(1, 6)]
    heard = "గేట్ నెంబర్ ఒకటి గేట్ నంబర్ రెండు గేట్ నంబర్ మూడు గేట్ నంబర్ నాలుగు గేట్ నంబర్ ఐదు"
    assert pairs(heard, "te") == [("gate", str(n)) for n in range(1, 6)]


def test_a_probe_transcript_of_ordinal_floors_gives_floors_and_the_landmark() -> None:
    heard = "ஆறாவது ஃப்ளோர் ஏழாவது ஃப்ளோர் எட்டாவது ஃப்ளோர் ஒன்பதாவது ஃப்ளோர் பத்தாவது ஃப்ளோர் பேக்கரி அருகில்"
    assert pairs(heard, "ta") == [("floor", str(n)) for n in range(6, 11)] + [
        ("landmark", "பேக்கரி")
    ]
    heard = "ఆరవ ఫ్లోర్ ఏడవ ఫ్లోర్ ఎనిమిదవ ఫ్లోర్ తొమ్మిదవ ఫ్లోర్ పదవ ఫ్లోర్ బేకరీ దగ్గర"
    assert pairs(heard, "te") == [("floor", str(n)) for n in range(6, 11)] + [
        ("landmark", "బేకరీ")
    ]
