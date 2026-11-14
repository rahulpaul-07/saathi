"""A landmark tile names the place, not the speaker (live test of Nov 14, finding F4).

Pronouns ("I") and forms of address ("brother") stand before the place name in a spoken
direction, so they must not end up inside the tile. And "the gate near the temple" is one
landmark, not a name plus a stray "wale gate".
"""

import pytest

from saathi.facts import extract_facts


def pairs(text: str, lang: str) -> list[tuple[str, str]]:
    return [(fact.kind, fact.value) for fact in extract_facts(text, lang)]


@pytest.mark.parametrize(
    ("lang", "text", "name"),
    [
        # The pronoun alone, the address alone, and both, in each script.
        ("hi", "मैं मंदिर के पास हूँ", "मंदिर"),
        ("hi", "मै मंदिर के पास हूँ", "मंदिर"),  # spelled without the anusvara
        ("hi", "भैया मंदिर के पास आओ", "मंदिर"),
        ("hi", "भैया मैं मंदिर के पास हूँ", "मंदिर"),
        ("hi", "भाई मैं गणेश मंदिर के सामने हूँ", "गणेश मंदिर"),
        ("bn", "আমি মন্দিরের কাছে গেটে আছি", "মন্দিরের"),
        ("bn", "দাদা মন্দিরের কাছে", "মন্দিরের"),
        ("bn", "দাদা আমি মন্দিরের কাছে আছি", "মন্দিরের"),
        ("bn", "আমি মন্দিরের গেটের সামনে আছি", "মন্দিরের গেটের"),
        ("kn", "ನಾನು ದೇವಸ್ಥಾನದ ಗೇಟ್ ಹತ್ತಿರ ಇದ್ದೇನೆ", "ದೇವಸ್ಥಾನದ ಗೇಟ್"),
        ("kn", "ಅಣ್ಣ ದೇವಸ್ಥಾನದ ಹತ್ತಿರ ಬನ್ನಿ", "ದೇವಸ್ಥಾನದ"),
        ("kn", "ಅಣ್ಣ ನಾನು ದೇವಸ್ಥಾನದ ಹತ್ತಿರ ಇದ್ದೇನೆ", "ದೇವಸ್ಥಾನದ"),
        ("kn", "ಅಕ್ಕ ನಾನು ಶಾಲೆ ಹತ್ತಿರ ಇದ್ದೇನೆ", "ಶಾಲೆ"),
        # After a "near" cue the name is read forward, and the pronoun that follows it is not part.
        ("hi", "नियर मंदिर मैं हूँ", "मंदिर"),
    ],
)
def test_a_pronoun_or_form_of_address_is_not_part_of_the_landmark(
    lang: str, text: str, name: str
) -> None:
    assert pairs(text, lang) == [("landmark", name)]


@pytest.mark.parametrize(
    ("lang", "text", "name"),
    [
        ("hi", "मैदान के पास", "मैदान"),  # starts like "मैं" but is the word for a ground
        ("hi", "मेन गेट के पास", "मेन गेट"),  # "main gate" written in Devanagari
        ("kn", "ಅಣ್ಣಮ್ಮ ದೇವಸ್ಥಾನದ ಹತ್ತಿರ", "ಅಣ್ಣಮ್ಮ ದೇವಸ್ಥಾನದ"),  # Annamma, a goddess, is not "anna"
        ("en", "bhaiya I am near the main gate", "main gate"),
    ],
)
def test_a_name_that_only_looks_like_a_person_word_is_kept(lang: str, text: str, name: str) -> None:
    assert pairs(text, lang) == [("landmark", name)]


@pytest.mark.parametrize(
    ("text", "name"),
    [
        # "the gate near the temple": the name, its postposition and the "wale gate" are one place.
        ("भैया मैं मंदिर के पास वाले गेट के पास हूँ", "मंदिर के पास वाले गेट"),
        ("भैया मैं मंदिर के सामने वाले गेट के पास हूँ", "मंदिर के सामने वाले गेट"),
        ("मैं मंदिर के सामने वाले गेट पर हूँ", "मंदिर के सामने वाले गेट"),  # one cue, then the gate
        ("मंदिर के पास वाली दुकान", "मंदिर के पास वाली दुकान"),  # the linker agrees with the noun
        ("भैया मैं मंदिर वाले गेट के पास हूँ", "मंदिर वाले गेट"),  # no postposition in between
    ],
)
def test_hindi_x_wale_gate_stays_one_landmark(text: str, name: str) -> None:
    (fact,) = extract_facts(text, "hi")
    assert (fact.kind, fact.value) == ("landmark", name)
    assert text[fact.start : fact.end] == fact.heard == name  # the tile points at what was said


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Two places that are not joined by a linker stay two landmarks.
        ("मंदिर के पास गेट के सामने", [("landmark", "मंदिर"), ("landmark", "गेट")]),
        # A linker with nothing after it joins nothing.
        ("मंदिर के पास वाले", [("landmark", "मंदिर")]),
        # A numbered gate keeps its own tile instead of being swallowed by the landmark.
        (
            "भैया मैं मंदिर के पास वाले गेट नंबर 2 पर हूँ",
            [("landmark", "मंदिर"), ("gate", "2")],
        ),
    ],
)
def test_the_wale_join_does_not_swallow_other_facts(
    text: str, expected: list[tuple[str, str]]
) -> None:
    assert pairs(text, "hi") == expected
