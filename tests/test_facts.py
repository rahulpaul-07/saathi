import pytest

from saathi.facts import MAX_TEXT_CHARS, Fact, extract_facts
from saathi.facts.text import key, tokenize


def pairs(text: str, lang: str) -> list[tuple[str, str]]:
    return [(fact.kind, fact.value) for fact in extract_facts(text, lang)]


def one(text: str, lang: str) -> Fact:
    (fact,) = extract_facts(text, lang)
    return fact


# --- normalization -----------------------------------------------------------------------------


def test_key_folds_the_spelling_variants_stt_produces() -> None:
    assert key("ಕ್ರಾಸ್") == key("ಕ್ರಾಸ")  # trailing virama
    assert key("फ़्लैट") == key("फ्लैट")  # nukta
    assert key("पाँच") == key("पांच")  # chandrabindu vs anusvara
    assert key("ಅಪಾರ್ಟ್‌ಮೆಂಟ್") == key("ಅಪಾರ್ಟ್ಮೆಂಟ್")  # ZWNJ
    assert key("৩০৪") == "304" and key("೩ನೇ") == "3ನೇ" and key("Gate") == "gate"


def test_tokenize_marks_punctuation_breaks() -> None:
    tokens = tokenize("gate 2, near temple")
    assert [t.break_after for t in tokens] == [False, True, False, True]


# --- English / universal layer -----------------------------------------------------------------


def test_english_directions_with_spans() -> None:
    text = "Second cross, third main, gate number 2, opposite the Ganesha temple."
    facts = extract_facts(text, "en")
    assert [(f.kind, f.value) for f in facts] == [
        ("cross", "2"),
        ("main", "3"),
        ("gate", "2"),
        ("landmark", "Ganesha temple"),
    ]
    assert [text[f.start : f.end] for f in facts] == [f.heard for f in facts]
    assert facts[0].heard == "Second cross" and facts[3].heard == "Ganesha temple"
    assert all(not f.ambiguous and f.reading is None for f in facts)


def test_english_digits_without_commas_do_not_steal_each_others_numbers() -> None:
    assert pairs("2nd cross 3rd main gate 2", "en") == [
        ("cross", "2"),
        ("main", "3"),
        ("gate", "2"),
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("gate twenty one", ("gate", "21")),
        ("flat two hundred and four", ("flat", "204")),
        ("flat three hundred", ("flat", "300")),
        ("flat 5B", ("flat", "5B")),
        ("block C", ("block", "C")),
        ("tower four", ("block", "4")),
        ("house number 14", ("flat", "14")),
        ("eleventh floor", ("floor", "11")),
        ("12th floor", ("floor", "12")),
    ],
)
def test_english_values(text: str, expected: tuple[str, str]) -> None:
    assert pairs(text, "en") == [expected]


def test_one_over_n_floor_is_read_as_floor_n_with_low_confidence() -> None:
    fact = one("1/4 floor", "en")
    assert (fact.kind, fact.value, fact.confidence) == ("floor", "4", "low")
    assert fact.heard == "1/4 floor"


def test_ambiguous_digit_run_is_surfaced_as_heard_not_guessed() -> None:
    fact = one("flat one four", "en")
    assert fact.ambiguous and fact.value == "one four" and fact.reading == "14"
    fact = one("flat 1 4", "en")
    assert fact.ambiguous and fact.value == "1 4" and fact.reading == "14"


def test_landmark_stops_at_punctuation_and_claimed_values() -> None:
    assert pairs("near gate 2", "en") == [("gate", "2")]  # no landmark: its words are the gate
    assert pairs("near the old bridge, turn left", "en") == [("landmark", "old bridge")]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello how are you",
        "gate",  # trigger without a value
        "gate number",
        "gate 500",  # out of range: noise, not a gate
        "floor 70",
        "block b",  # a lowercase lone letter is not a label
        "opposite, the temple",  # punctuation separates trigger and name
        "2 gate",  # a bare value before a trigger that needs "number" is not enough
        "gate 12345",  # too many digits to be a gate
    ],
)
def test_nothing_is_extracted_when_the_pattern_is_not_there(text: str) -> None:
    assert pairs(text, "en") == []


def test_the_pronoun_i_is_not_a_letter_label() -> None:
    assert pairs("flat 402 I will wait", "en") == [("flat", "402")]


def test_a_value_is_not_claimed_by_two_facts() -> None:
    # "3" belongs to the gate (explicit trigger-first); main may not reuse it.
    assert pairs("gate 3 main", "en") == [("gate", "3")]


# --- Kannada (forms from the probe) ------------------------------------------------------------


def test_kannada_probe_forms() -> None:
    text = "ಎರಡನೇ ಕ್ರಾಸ್, ಮೂರನೇ ಮೇನ್, ಗೇಟ್ ನಂಬರ್ ಎರಡು ಹತ್ತಿರ, ಆಪೋಸಿಟ್ ಗಣೇಶ ದೇವಸ್ಥಾನ"
    assert pairs(text, "kn") == [
        ("cross", "2"),
        ("main", "3"),
        ("gate", "2"),
        ("landmark", "ಗಣೇಶ ದೇವಸ್ಥಾನ"),
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ಫ್ಲ್ಯಾಟ್ ಮುನ್ನೂರ ನಾಲ್ಕು", ("flat", "304")),  # probe: 304 as words
        ("ಫ್ಲಾಟ್ ಮುನ್ನೂರ ನಾಲ್ಕು", ("flat", "304")),  # probe: second spelling of flat
        ("ಎರಡು ನೇ ಕ್ರಾಸ್", ("cross", "2")),  # probe: split ordinal
        ("ಮೂರನೇ ಕ್ರಾಸ", ("cross", "3")),  # trigger written without its final virama
        ("ಥರ್ಡ್ ಫ್ಲೋರ್", ("floor", "3")),  # probe: English ordinal in Kannada script
        ("ಫ್ಲಾಟ್ ಫೈವ್ ಬಿ", ("flat", "5B")),  # probe: number plus spoken letter
        ("ಬ್ಲಾಕ್ ಫೋರ್", ("block", "4")),
        ("ಟವರ್ ಬಿ", ("block", "B")),
        ("ಗೇಟ್ ನಂಬರ್ ಇಪ್ಪತ್ತೊಂದು", ("gate", "21")),  # tens + unit sandhi
        ("ಹದಿನೈದನೇ ಮೇನ್", ("main", "15")),
        ("೩ನೇ ಮೇನ್", ("main", "3")),  # Kannada digit with the -ನೇ suffix
        ("ಎರಡನೇ ಮಹಡಿ", ("floor", "2")),
        ("gate number 2", ("gate", "2")),  # universal layer inside a Kannada transcript
    ],
)
def test_kannada_values(text: str, expected: tuple[str, str]) -> None:
    assert pairs(text, "kn") == [expected]


def test_kannada_digit_by_digit_is_ambiguous() -> None:
    fact = one("ಹೌಸ್ ನಂಬರ್ ಒಂದು ನಾಲ್ಕು", "kn")  # probe: 14 came out as "ಒಂದು ನಾಲ್ಕು"
    assert (fact.kind, fact.value, fact.reading) == ("flat", "ಒಂದು ನಾಲ್ಕು", "14")
    assert fact.ambiguous


def test_kannada_landmark_before_a_postposition() -> None:
    assert pairs("ಸೈಕಲ್ ಅಂಗಡಿ ಪಕ್ಕ ಲೆಫ್ಟ್ ತಗೊಳ್ಳಿ", "kn") == [("landmark", "ಸೈಕಲ್ ಅಂಗಡಿ")]
    fact = one("ನಮ್ಮ ಮನೆ ಗಣೇಶ ದೇವಸ್ಥಾನದ ಎದುರು", "kn")  # "our house" is not part of the name
    assert fact.value == "ಗಣೇಶ ದೇವಸ್ಥಾನದ" and fact.confidence == "low"


@pytest.mark.parametrize("text", ["ಗೇಟ್ ನಂಬರ್ ಬನ್ನಿ", "ಗೇಟ್ ನಂಬರ್ ಹತ್ತಿರ ಬನ್ನಿ"])
def test_kannada_unknown_value_gives_nothing(text: str) -> None:
    assert pairs(text, "kn") == []


def test_kannada_postposition_does_not_swallow_a_gate() -> None:
    assert pairs("ಗೇಟ್ ನಂಬರ್ ಎರಡು ಹತ್ತಿರ ಬನ್ನಿ", "kn") == [("gate", "2")]


# --- Hindi -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("फ्लैट तीन सौ चार", ("flat", "304")),
        ("फ़्लैट 502", ("flat", "502")),  # nukta variant
        ("पाँचवीं मंजिल", ("floor", "5")),
        ("दूसरे क्रॉस", ("cross", "2")),
        ("गेट नंबर दो", ("gate", "2")),
        ("ब्लॉक सी", ("block", "C")),
        ("सेकंड फ्लोर", ("floor", "2")),
        ("गेट नंबर पच्चीस", ("gate", "25")),
    ],
)
def test_hindi_values(text: str, expected: tuple[str, str]) -> None:
    assert pairs(text, "hi") == [expected]


def test_hindi_landmark_drops_the_genitive_particle() -> None:
    fact = one("गणेश मंदिर के सामने", "hi")
    assert fact.value == "गणेश मंदिर" and fact.confidence == "low"
    assert pairs("गेट नंबर दो के पास", "hi") == [("gate", "2")]


def test_hindi_failure_paths() -> None:
    assert pairs("गेट नंबर", "hi") == []
    assert pairs("चौथी", "hi") == []  # an ordinal with no trigger is nothing


# --- Bengali -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ফ্ল্যাট ৩০৪", ("flat", "304")),  # Bengali digits
        ("দুই নম্বর ক্রস", ("cross", "2")),  # value, filler, trigger
        ("গেট নম্বর দুই", ("gate", "2")),
        ("তৃতীয় তলা", ("floor", "3")),
        ("পাঁচ তলা", ("floor", "5")),
        ("ফ্ল্যাট একশো দুই", ("flat", "102")),
        ("ফ্ল্যাট তিনশো চার", ("flat", "304")),
        ("চার নম্বর গেট", ("gate", "4")),
        ("ব্লক সি", ("block", "C")),
    ],
)
def test_bengali_values(text: str, expected: tuple[str, str]) -> None:
    assert pairs(text, "bn") == [expected]


def test_bengali_landmark_and_failure() -> None:
    assert pairs("স্কুলের পেছনে", "bn") == [("landmark", "স্কুলের")]
    assert pairs("2 গেট", "bn") == []  # bare value before a gate needs the filler
    assert pairs("গেট নম্বর", "bn") == []


# --- Other languages and the boundary ----------------------------------------------------------


def test_languages_without_native_rules_get_only_the_universal_layer() -> None:
    assert pairs("gate number 2, 3rd main", "ta") == [("gate", "2"), ("main", "3")]
    assert pairs("கேட் நம்பர் இரண்டு", "ta") == []  # native words are a stated limit


def test_unsupported_language_and_oversized_text_are_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported language"):
        extract_facts("gate 2", "or")
    with pytest.raises(ValueError, match="longer than"):
        extract_facts("a" * (MAX_TEXT_CHARS + 1), "en")


def test_every_language_in_the_table_gets_the_universal_layer() -> None:
    # Extraction depends only on the spoken language, never on who speaks, so a rider's turn in any
    # of the 10 languages is treated exactly like a customer's.
    from saathi.languages import LANGUAGES

    assert len(LANGUAGES) == 10
    for code in LANGUAGES:
        assert pairs("gate number 2, 3rd main", code) == [("gate", "2"), ("main", "3")]
