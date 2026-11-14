"""Door, house and room numbers make a flat fact (live test of Nov 14, finding F2).

A door, room or house word names a flat only beside "number": alone it is an ordinary word ("the
third door", "open the door"), so a bare number after it is not enough.
"""

import pytest

from saathi.facts import extract_facts

# "Brother, not 56, come to door number 57": the number comes first, then "number", then "door".
KN_LIVE = "ಅಣ್ಣ, ಐವತ್ತಾರು ಅಲ್ಲ, ಐವತ್ತೇಳು ನಂಬರ್ ಡೋರ್ ಗೆ ಬನ್ನಿ"


def pairs(text: str, lang: str) -> list[tuple[str, str]]:
    return [(fact.kind, fact.value) for fact in extract_facts(text, lang)]


def test_the_live_kannada_sentence_makes_a_flat_tile_for_the_corrected_number() -> None:
    (fact,) = extract_facts(KN_LIVE, "kn")
    assert (fact.kind, fact.value, fact.ambiguous) == ("flat", "57", False)
    assert fact.heard == "ಐವತ್ತೇಳು ನಂಬರ್ ಡೋರ್"  # the tile shows what was said, not "56"


@pytest.mark.parametrize(
    ("lang", "text", "value"),
    [
        ("en", "door number 57", "57"),
        ("en", "room number 304", "304"),
        ("en", "57 number door", "57"),
        ("en", "come to door no 12", "12"),
        ("en", "door number fifty seven", "57"),
        ("kn", "ಡೋರ್ ನಂಬರ್ ಐವತ್ತೇಳು", "57"),
        ("kn", "ಐವತ್ತೇಳು ನಂಬರ್ ಡೋರ್", "57"),
        ("kn", "57 ನಂಬರ್ ಡೋರ್ ಗೆ ಬನ್ನಿ", "57"),
        ("kn", "ರೂಮ್ ನಂಬರ್ ಮುನ್ನೂರ ನಾಲ್ಕು", "304"),
        ("kn", "ಮನೆ ನಂಬರ್ ಹನ್ನೆರಡು", "12"),
        ("hi", "दरवाजा नंबर 57", "57"),
        ("hi", "दरवाज़ा नंबर 57", "57"),  # nukta variant
        ("hi", "सत्तावन नंबर दरवाजा", "57"),
        ("hi", "कमरा नंबर 304", "304"),
        ("hi", "घर नंबर बारह", "12"),
        ("bn", "দরজা নম্বর ৫৭", "57"),
        ("bn", "সাতান্ন নম্বর দরজা", "57"),
        ("bn", "৫৭ নম্বর ঘরে আসুন", "57"),
        ("bn", "রুম নম্বর ৩০৪", "304"),
        ("bn", "বাড়ি নম্বর বারো", "12"),
        # The words that were already flat triggers now also read "57 number house".
        ("en", "57 number house", "57"),
        ("en", "57 number flat", "57"),
        ("kn", "ಐವತ್ತೇಳು ನಂಬರ್ ಫ್ಲಾಟ್", "57"),
    ],
)
def test_a_door_house_or_room_number_is_a_flat(lang: str, text: str, value: str) -> None:
    assert pairs(text, lang) == [("flat", value)]


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("hi", "57 नंबर के दरवाजे पर आओ"),  # the genitive between "number" and the door
        ("hi", "57 नंबर का मकान"),
    ],
)
def test_a_hindi_genitive_links_the_number_to_the_door(lang: str, text: str) -> None:
    (fact,) = extract_facts(text, lang)
    assert (fact.kind, fact.value) == ("flat", "57")
    assert fact.heard == text.removesuffix(" पर आओ")


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "the third door on the left"),
        ("en", "open the door"),
        ("en", "door number"),  # no value
        ("en", "room 304"),  # a bare number after door or room is not enough
        ("en", "57 flat"),  # a bare value before a flat word is not enough either
        ("en", "door 5 meters ahead"),
        ("kn", "ಮೂರನೇ ಡೋರ್"),
        ("kn", "ಡೋರ್ ತೆರೆಯಿರಿ"),
        ("hi", "तीसरा दरवाजा"),
        ("hi", "कमरे में आओ"),
        ("hi", "घर 5 मिनट दूर है"),
        ("bn", "তৃতীয় দরজা"),
        ("bn", "ঘরে আসুন"),
    ],
)
def test_a_door_room_or_house_word_without_a_number_is_not_a_flat(lang: str, text: str) -> None:
    assert pairs(text, lang) == []


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("kn", "ಅಣ್ಣ ಐವತ್ತಾರು ಅಲ್ಲ ಐವತ್ತೇಳು ನಂಬರ್ ಡೋರ್ ಗೆ ಬನ್ನಿ"),  # the live sentence, no commas
        ("bn", "দাদা ৫৬ না ৫৭ নম্বর ঘরে আসুন"),
        ("hi", "भाई 56 नहीं 57 नंबर के दरवाजे पर आओ"),
    ],
)
def test_a_correction_without_commas_keeps_the_number_that_names_the_door(
    lang: str, text: str
) -> None:
    # "56 not 57 number door": the 57 runs into the door word, so it is a new value and not the
    # one a following "not" takes back. Without that rule the tile showed the retracted 56.
    assert pairs(text, lang) == [("flat", "57")]


def test_a_rejected_value_after_a_door_number_is_dropped() -> None:
    assert pairs("come to door number 57 not 56", "en") == [("flat", "57")]
    assert pairs("door number 57, not 56", "en") == [("flat", "57")]


def test_a_door_number_and_a_gate_number_keep_their_own_values() -> None:
    assert pairs("gate number 2, door number 57", "en") == [("gate", "2"), ("flat", "57")]
    assert pairs("door number 57 gate number 2", "en") == [("flat", "57"), ("gate", "2")]
    assert pairs("57 number door gate number 2", "en") == [("flat", "57"), ("gate", "2")]


def test_a_gate_number_before_a_genitive_door_is_not_read_as_a_door_number() -> None:
    # "के दरवाजे" follows the gate's value, which is not a "number" word: nothing to link.
    assert pairs("गेट नंबर 2 के दरवाजे पर", "hi") == [("gate", "2")]
