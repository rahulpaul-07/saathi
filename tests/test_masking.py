import pytest

from placeholders import carry
from saathi.facts import extract_facts
from saathi.facts.text import key
from saathi.languages import LANGUAGES
from saathi.loanwords import CONCEPTS, SPOKEN_CONCEPTS, concept_of, written
from saathi.masking import FIRST_SLOT, mask, ordinal_word, restore, translate_masked
from saathi.quickreplies import QUICK_REPLIES

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
