import pytest

from placeholders import carry
from saathi.facts import extract_facts
from saathi.facts.text import key
from saathi.languages import LANGUAGES
from saathi.loanwords import CONCEPTS, SPOKEN_CONCEPTS, concept_of, written
from saathi.masking import FIRST_SLOT, mask, restore, translate_masked

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
