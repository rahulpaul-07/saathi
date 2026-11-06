"""Spoken corrections with "not": the rejected value is dropped, in both word orders.

"gate number 2, 4 not" keeps 2; "sorry, gate number 4, not 2" keeps 4. Words are spellings the real
STT wrote (docs/EVAL.md first-pass table) or the plain word for "not".
"""

import pytest

from saathi.facts import extract_facts

# language -> (gate, number, two, four, not)
_WORDS = {
    "en": ("gate", "number", "two", "four", "not"),
    "hi": ("गेट", "नंबर", "दो", "चार", "नहीं"),
    "bn": ("গেট", "নম্বর", "দুই", "চার", "না"),
    "mr": ("गेट", "नंबर", "दोन", "चार", "नाही"),
    "pa": ("ਗੇਟ", "ਨੰਬਰ", "ਦੋ", "ਚਾਰ", "ਨਹੀਂ"),
    "gu": ("ગેટ", "નંબર", "બે", "ચાર", "નહીં"),
    "kn": ("ಗೇಟ್", "ನಂಬರ್", "ಎರಡು", "ನಾಲ್ಕು", "ಅಲ್ಲ"),
    "ta": ("கேட்", "நம்பர்", "இரண்டு", "நான்கு", "இல்லை"),
}


def _gate(text: str, language: str) -> list[str]:
    return [fact.value for fact in extract_facts(text, language) if fact.kind == "gate"]


@pytest.mark.parametrize("language", sorted(_WORDS))
def test_value_then_rejected_value_then_not_keeps_the_first(language: str) -> None:
    gate, number, two, four, neg = _WORDS[language]
    assert _gate(f"{gate} {number} {two}, {four} {neg}", language) == ["2"]


@pytest.mark.parametrize("language", sorted(_WORDS))
def test_digits_run_then_not_keeps_the_first(language: str) -> None:
    # The STT writes the spoken "two, four" as one digit run: "2 4 नहीं".
    gate, number, _two, _four, neg = _WORDS[language]
    assert _gate(f"{gate} {number} 2 4 {neg}", language) == ["2"]


@pytest.mark.parametrize("language", sorted(_WORDS))
def test_value_then_not_then_the_wrong_value_keeps_the_first(language: str) -> None:
    gate, number, two, four, neg = _WORDS[language]
    assert _gate(f"sorry {gate} {number} {four}, {neg} {two}", language) == ["4"]


@pytest.mark.parametrize("language", sorted(_WORDS))
def test_text_without_a_negation_is_unchanged(language: str) -> None:
    gate, number, two, four, _neg = _WORDS[language]
    # Last fact of a kind wins within a turn: a plain correction still replaces the mistake.
    assert _gate(f"{gate} {number} {four}, {gate} {number} {two}", language) == ["4", "2"]


def test_a_rejected_value_before_a_trigger_is_a_new_fact_and_is_kept() -> None:
    facts = extract_facts("gate 4, not 2 floor", "en")
    assert [(f.kind, f.value) for f in facts] == [("gate", "4"), ("floor", "2")]


def test_a_compound_number_is_not_split() -> None:
    assert _gate("gate number twenty four not", "en") == ["24"]


def test_not_without_a_number_on_either_side_changes_nothing() -> None:
    assert _gate("gate number 3 not far", "en") == ["3"]


def test_marathi_cue_glued_to_the_name_is_split_off() -> None:
    facts = extract_facts("गेट नंबर एक स्कूलसमोर", "mr")
    landmarks = [f.value for f in facts if f.kind == "landmark"]
    assert landmarks == ["स्कूल"]


def test_marathi_glued_cue_after_a_two_word_name() -> None:
    facts = extract_facts("बस स्टॉपसमोर", "mr")
    assert [f.value for f in facts if f.kind == "landmark"] == ["बस स्टॉप"]


def test_marathi_separate_cue_still_works() -> None:
    facts = extract_facts("फार्मसी मागे", "mr")
    assert [f.value for f in facts if f.kind == "landmark"] == ["फार्मसी"]


def test_a_bare_marathi_cue_is_not_a_landmark() -> None:
    assert [f for f in extract_facts("समोर", "mr") if f.kind == "landmark"] == []


def test_gujarati_main_in_the_stt_spelling() -> None:
    facts = extract_facts("ત્રીજો મેઈન", "gu")
    assert [(f.kind, f.value) for f in facts] == [("main", "3")]
