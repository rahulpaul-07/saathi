import re

import pytest

from placeholders import carry
from saathi.facts import extract_facts
from saathi.facts.lexicons import lexicon_for
from saathi.facts.numbers import Number, parse_number
from saathi.facts.text import key, tokenize
from saathi.languages import LANGUAGES
from saathi.loanwords import CONCEPTS, SPOKEN_CONCEPTS, concept_of, written
from saathi.masking import FIRST_SLOT, mask, ordinal_word, restore, translate_masked
from saathi.quickreplies import QUICK_REPLIES
from saathi.translate import RoutingTranslator

EN = "second cross third main gate number 5"  # synthetic


class Replay:
    """Returns a fixed string, ignoring the input."""

    def __init__(self, output: str) -> None:
        self.output = output

    def translate(self, text: str, src: str, tgt: str) -> str:
        return self.output


def test_every_concept_has_a_spelling_in_every_language() -> None:
    for concept in CONCEPTS:
        for language in LANGUAGES:
            assert written(concept, language)


def test_written_spelling_is_recognised_back_for_spoken_concepts() -> None:
    for concept in SPOKEN_CONCEPTS:
        for language in LANGUAGES:
            assert concept_of(key(written(concept, language)), language) == concept


def test_fact_value_spans_cover_the_number_words() -> None:
    facts = extract_facts(EN, "en")
    cross = next(f for f in facts if f.kind == "cross")
    assert cross.value_start is not None and cross.value_end is not None
    assert EN[cross.value_start : cross.value_end] == "second"


def test_mask_replaces_values_and_loanwords_with_numbered_slots() -> None:
    masked = mask(EN, "en", extract_facts(EN, "en"))
    assert masked.text.startswith("#L51 #L52 #L53 #L54 #L55 ")
    assert [slot.number for slot in masked.slots][0] == FIRST_SLOT
    loanwords = {slot.text for slot in masked.slots if slot.kind == "loanword"}
    assert loanwords >= {"cross", "main", "gate"}
    assert {slot.text for slot in masked.slots if slot.kind == "value"} == {"2", "3", "5"}


def test_round_trip_restores_digits_and_the_listeners_spelling() -> None:
    result = translate_masked(_Carry(), EN, "en", "kn")
    assert result.verified is True
    assert "5" in result.text and written("gate", "kn") in result.text
    assert "#" not in result.text


class _Carry:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return carry("", text)


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_restored_text_has_only_plain_digits_in_every_language(language: str) -> None:
    masked = mask(EN, "en", extract_facts(EN, "en"))
    slots = " ".join(f"#L{slot.number}" for slot in masked.slots)
    native = "৫ ० ೩ ൨"  # Bengali 5, Devanagari 0, Kannada 3, Malayalam 2
    restored = restore(f"{slots} {native}", masked, language)
    assert restored.text.endswith("5 0 3 2")
    assert all(ch.isascii() for ch in restored.text if ch.isdecimal())


def test_quick_replies_use_plain_digits() -> None:
    for phrases in QUICK_REPLIES.values():
        for phrase in phrases.values():
            assert all(ch.isascii() for ch in phrase.text if ch.isdecimal())


def test_a_lost_placeholder_is_unverified() -> None:
    masked = mask(EN, "en", extract_facts(EN, "en"))
    kept = " ".join(f"#L{slot.number}" for slot in masked.slots[:-1])
    assert restore(kept, masked, "kn").verified is False


def test_a_duplicated_placeholder_is_unverified() -> None:
    masked = mask(EN, "en", extract_facts(EN, "en"))
    everything = " ".join(f"#L{slot.number}" for slot in masked.slots)
    assert restore(everything + " #L51", masked, "kn").verified is False


def test_an_invented_placeholder_is_unverified_and_left_in_place() -> None:
    masked = mask("gate 5", "en", extract_facts("gate 5", "en"))
    restored = restore("#L51 #L52 #L99", masked, "kn")
    assert restored.verified is False
    assert "#L99" in restored.text


def test_text_without_slots_is_verified_and_untouched() -> None:
    masked = mask("hello there", "en", [])
    assert masked.slots == ()
    assert restore("namaskara", masked, "kn") == restore("namaskara", masked, "kn")
    assert restore("namaskara", masked, "kn").verified is True


def test_ambiguous_readings_are_not_masked() -> None:
    text = "flat one four"
    facts = extract_facts(text, "en")
    assert any(f.ambiguous for f in facts)
    assert all(slot.kind != "value" for slot in mask(text, "en", facts).slots)


def test_unknown_source_language_is_rejected() -> None:
    with pytest.raises(ValueError):
        translate_masked(Replay("x"), "gate 5", "xx", "kn")


# --- conditional masking -----------------------------------------------------------------------


def test_default_mode_masks_every_value_as_a_plain_value() -> None:
    masked = mask(EN, "en", extract_facts(EN, "en"), tgt="hi")
    assert {slot.kind for slot in masked.slots} == {"loanword", "value"}


def test_conditional_masks_ordinal_kinds_as_ordinal_slots_and_gate_as_a_value() -> None:
    masked = mask(EN, "en", extract_facts(EN, "en"), tgt="hi", mode="conditional")
    assert {slot.text for slot in masked.slots if slot.kind == "ordinal"} == {"2", "3"}
    assert {slot.text for slot in masked.slots if slot.kind == "value"} == {"5"}


def test_conditional_restores_the_ordinal_word_in_the_target_language() -> None:
    result = translate_masked(_Carry(), EN, "en", "hi", mode="conditional")
    assert result.verified is True
    for value in ("2", "3"):
        word = ordinal_word(value, "hi")
        assert word is not None and word in result.text
    assert "2" not in result.text and "3" not in result.text  # no bare digit: the ordinal is spoken
    assert "5" in result.text  # the gate stays a digit


def test_conditional_leaves_the_value_unmasked_where_the_target_has_no_ordinal_word() -> None:
    assert ordinal_word("2", "bn") is None  # Bengali is excluded: the lexicon spelling is folded
    masked = mask(EN, "en", extract_facts(EN, "en"), tgt="bn", mode="conditional")
    assert not [slot for slot in masked.slots if slot.kind == "ordinal"]
    assert masked.text.startswith("second ") or " second " in masked.text


def test_conditional_leaves_values_without_an_ordinal_word_unmasked() -> None:
    text = "35th floor"  # beyond the 20 ordinals most lexicons list
    masked = mask(text, "en", extract_facts(text, "en"), tgt="gu", mode="conditional")
    assert masked.text == "35th #L51"
    assert [slot.kind for slot in masked.slots] == ["loanword"]


def test_conditional_needs_a_target_language() -> None:
    with pytest.raises(ValueError, match="target"):
        mask(EN, "en", extract_facts(EN, "en"), mode="conditional")


def test_conditional_still_flags_a_lost_ordinal_slot() -> None:
    result = translate_masked(Replay("#L51 only"), EN, "en", "hi", mode="conditional")
    assert result.verified is False


def test_ordinal_word_rejects_non_numeric_values() -> None:
    assert ordinal_word("5B", "en") is None
    assert ordinal_word("2", "en") == "second"
    assert ordinal_word("99", "en") is None


# --- numbers no fact owns ----------------------------------------------------------------------
# Live test with a native Kannada speaker: a number that was not beside a gate, flat or floor word
# went to the model as words, and "not 56, 57" reached the rider as "500, 507".

KN_NOT_56_BUT_57 = "ಅಣ್ಣ, ಐವತ್ತಾರು ಅಲ್ಲ, ಐವತ್ತೇಳು ನಂಬರ್ ಡೋರ್ ಗೆ ಬನ್ನಿ"
KN_77 = "ಎಪ್ಪತ್ತೇಳು ನಂಬರ್ ಡೋರ್ ಗೆ ಬನ್ನಿ"


def _locked_values(text: str, src: str) -> list[str]:
    masked = mask(text, src, extract_facts(text, src))
    return [slot.text for slot in masked.slots if slot.kind == "value"]


def _first_number(text: str, src: str) -> Number:
    """The first number the grammar reads, so a test cannot pass by the text having none."""
    lexicon = lexicon_for(src)
    tokens = tokenize(text)
    for index in range(len(tokens)):
        number = parse_number(tokens, index, lexicon)
        if number is not None:
            return number
    raise AssertionError(f"no number read in {text!r}")


def test_every_number_in_the_source_is_locked_not_only_those_beside_a_fact_word() -> None:
    masked = mask(KN_NOT_56_BUT_57, "kn", extract_facts(KN_NOT_56_BUT_57, "kn"))
    assert masked.text == "ಅಣ್ಣ, #L51 ಅಲ್ಲ, #L52 ನಂಬರ್ ಡೋರ್ ಗೆ ಬನ್ನಿ"
    assert [(slot.number, slot.kind, slot.text) for slot in masked.slots] == [
        (51, "value", "56"),
        (52, "value", "57"),
    ]


def test_a_seventy_seven_is_locked_so_the_model_cannot_turn_it_into_a_fifty() -> None:
    assert _locked_values(KN_77, "kn") == ["77"]


@pytest.mark.parametrize("tgt", ["bn", "hi", "en"])
def test_locked_numbers_reach_the_riders_sentence_as_digits(tgt: str) -> None:
    result = translate_masked(_Carry(), KN_NOT_56_BUT_57, "kn", tgt)
    assert result.verified is True
    assert result.text.split() == ["56", "57"]


def test_a_lost_number_placeholder_is_unverified_not_silent() -> None:
    masked = mask(KN_NOT_56_BUT_57, "kn", extract_facts(KN_NOT_56_BUT_57, "kn"))
    assert restore("#L51 #L52", masked, "bn").verified is True
    assert restore("#L51", masked, "bn").verified is False
    assert restore("#L51 #L52 #L52", masked, "bn").verified is False


@pytest.mark.parametrize(
    ("src", "text", "value"),
    [
        ("kn", "5 ನಿಮಿಷದಲ್ಲಿ ಬರುತ್ತೇನೆ", "5"),
        ("kn", "೫೭ ಮೀಟರ್ ನೇರ ಹೋಗಿ", "57"),  # Kannada digits are locked and come back as 0-9
        ("hi", "५७ मीटर सीधे जाइए", "57"),
        ("bn", "৫৯ মিটার সোজা যান", "59"),
        ("en", "wait 12 minutes", "12"),
    ],
)
def test_digits_are_locked_in_any_script(src: str, text: str, value: str) -> None:
    assert _locked_values(text, src) == [value]


@pytest.mark.parametrize(
    ("src", "text", "value"),
    [
        ("kn", "ಹತ್ತು ನಿಮಿಷದಲ್ಲಿ ಬರುತ್ತೇನೆ", "10"),
        ("hi", "पचास मीटर सीधे जाइए", "50"),
        ("hi", "सौ मीटर आगे", "100"),
        ("bn", "ঊনষাট মিটার সোজা যান", "59"),
        ("bn", "উনষাট মিটার সোজা যান", "59"),  # the short vowel in the prefix (finding F3)
        ("bn", "ঊন ষাট মিটার সোজা যান", "59"),  # the prefix as its own word, not a lone 60
        ("en", "fifty seven meters straight", "57"),  # two words, one number, one slot
    ],
)
def test_number_words_from_ten_up_are_locked(src: str, text: str, value: str) -> None:
    assert _locked_values(text, src) == [value]


@pytest.mark.parametrize(
    ("src", "text"),
    [
        ("kn", "ಒಂದು ನಿಮಿಷ ಇರಿ"),  # "one" is also "a"
        ("hi", "एक मिनट रुकिए"),  # "one" is also "a"
        ("hi", "मुझे दो मिनट दो"),  # "do" is "two" and "give"
        ("bn", "এক মিনিট দাঁড়ান"),  # "one" is also "a"
        ("bn", "এটা নয়"),  # "noy" is "nine" and "not"
        ("en", "wait one minute"),
    ],
)
def test_words_below_ten_are_left_to_the_model(src: str, text: str) -> None:
    assert _first_number(text, src).magnitude < 10
    masked = mask(text, src, extract_facts(text, src))
    assert masked.slots == () and masked.text == text


@pytest.mark.parametrize(
    ("src", "text"),
    [
        ("en", "take the third door"),
        ("en", "take the 12th lane"),  # an ordinal of ten or more is still an ordinal
        ("hi", "तीसरा दरवाजा"),
        ("kn", "12ನೇ ಬಾಗಿಲು"),
    ],
)
def test_ordinals_are_never_locked_as_plain_numbers(src: str, text: str) -> None:
    assert _first_number(text, src).ordinal is True
    masked = mask(text, src, extract_facts(text, src))
    assert masked.slots == () and masked.text == text


def test_an_ambiguous_digit_run_is_left_whole() -> None:
    text = "wait 2 4 minutes"
    assert _first_number(text, "en").ambiguous is True
    assert mask(text, "en", extract_facts(text, "en")).slots == ()


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "it is 2.5 km"),
        ("en", "come at 5:30"),
        ("en", "wait 10-12 minutes"),
        ("en", "it is 1,000 meters"),
        ("en", "twenty first lane"),
        ("hi", "2 सौ मीटर आगे"),
    ],
)
def test_numbers_that_touch_are_one_figure_and_left_to_the_model(lang: str, text: str) -> None:
    # Locking half of "2.5" or "2 सौ" would put a wrong number in the sentence.
    assert mask(text, lang, extract_facts(text, lang)).slots == ()


def test_a_list_of_numbers_is_locked_number_by_number() -> None:
    assert _locked_values("it is 56, 57 or 58", "en") == ["56", "57", "58"]


def test_a_lone_bengali_hundred_suffix_is_an_ordinary_word_not_a_100() -> None:
    text = "মারুতি শো রুমের সামনে"  # "in front of the Maruti show room"
    masked = mask(text, "bn", extract_facts(text, "bn"))
    assert masked.slots == () and masked.text == text


@pytest.mark.parametrize("text", ["একশো মিটার সোজা যান", "এক শো মিটার সোজা যান"])
def test_a_bengali_hundred_with_its_unit_is_locked(text: str) -> None:
    assert _locked_values(text, "bn") == ["100"]


def test_a_number_beside_a_fact_word_is_locked_once() -> None:
    text = "gate number fifty seven"
    masked = mask(text, "en", extract_facts(text, "en"))
    assert [slot.text for slot in masked.slots if slot.kind == "value"] == ["57"]


def test_conditional_masking_leaves_a_value_it_declined_to_lock_alone() -> None:
    text = "21 cross"  # Gujarati has no ordinal word for 21: the value stays in the text on purpose
    assert [(f.kind, f.value) for f in extract_facts(text, "en")] == [("cross", "21")]
    masked = mask(text, "en", extract_facts(text, "en"), tgt="gu", mode="conditional")
    assert masked.text == "21 #L51"
    assert [slot.kind for slot in masked.slots] == ["loanword"]


def test_text_without_a_number_is_unchanged_by_number_locking() -> None:
    masked = mask("ಅಣ್ಣ ಬನ್ನಿ", "kn", [])
    assert masked.slots == () and masked.text == "ಅಣ್ಣ ಬನ್ನಿ"


@pytest.fixture(scope="module")
def routing_translator() -> RoutingTranslator:
    return RoutingTranslator()


@pytest.mark.model
@pytest.mark.parametrize("tgt", ["bn", "hi", "en"])
@pytest.mark.parametrize(("text", "digits"), [(KN_NOT_56_BUT_57, ["56", "57"]), (KN_77, ["77"])])
def test_real_model_carries_the_locked_numbers_to_the_rider(
    routing_translator: RoutingTranslator, text: str, digits: list[str], tgt: str
) -> None:
    result = translate_masked(routing_translator, text, "kn", tgt)
    assert result.verified is True, result.raw
    # The multiset, not the order: English may say "door 57, not 56" for "not 56, 57".
    assert sorted(re.findall(r"\d+", result.text)) == sorted(digits), result.text
