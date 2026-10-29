import dataclasses

import pytest

from saathi.facts import extract_facts
from saathi.landmarks import localize_landmarks, plausible
from saathi.loanwords import written
from saathi.summary import fact_summary
from saathi.translate import DegenerateTranslationError

TEXT = "second cross third main gate number 5 opposite blue temple"  # synthetic


class Fixed:
    def __init__(self, output: str | Exception) -> None:
        self.output = output

    def translate(self, text: str, src: str, tgt: str) -> str:
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def test_summary_is_value_first_for_numbers_that_read_that_way() -> None:
    facts = extract_facts("second cross third main gate number 5", "en")
    cross, main, gate = (written(k, "kn") for k in ("cross", "main", "gate"))
    assert fact_summary(facts, "kn") == f"2 {cross}, 3 {main}, {gate} 5"


def test_summary_round_trips_through_the_extractor() -> None:
    facts = extract_facts("second cross third main gate number 5", "en")
    for tgt in ("kn", "hi", "bn"):
        again = extract_facts(fact_summary(facts, tgt), tgt)
        assert sorted((f.kind, f.value) for f in again) == sorted((f.kind, f.value) for f in facts)


def test_summary_skips_a_landmark_without_a_local_name() -> None:
    facts = extract_facts(TEXT, "en")
    assert "temple" not in fact_summary(facts, "kn")
    assert fact_summary([], "kn") == ""


def test_summary_includes_a_localized_landmark() -> None:
    facts = [dataclasses.replace(f, local="ದೇವಸ್ಥಾನ") if f.kind == "landmark" else f
             for f in extract_facts(TEXT, "en")]
    assert fact_summary(facts, "kn").endswith("ದೇವಸ್ಥಾನ")


@pytest.mark.parametrize(
    ("translated", "ok"),
    [
        ("ದೇವಸ್ಥಾನ", True),
        ("", False),
        ("ದೇವಸ್ಥಾನ #L51", False),
        ("temple", False),  # Latin text for a Kannada listener
        ("ದೇವ" * 40, False),  # runaway length
        ("ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ", False),
    ],
)
def test_plausible(translated: str, ok: bool) -> None:
    assert plausible(translated, "blue temple", "kn") is ok


def _landmarks(output: str | Exception) -> tuple[str | None, ...]:
    facts = extract_facts(TEXT, "en")
    done = localize_landmarks(facts, "en", "kn", Fixed(output))
    return tuple(f.local for f in done if f.kind == "landmark")


def test_a_plausible_translation_becomes_the_local_name() -> None:
    assert _landmarks("ನೀಲಿ ದೇವಸ್ಥಾನ") == ("ನೀಲಿ ದೇವಸ್ಥಾನ",)


def test_an_implausible_or_failing_translation_falls_back_to_class_only() -> None:
    assert _landmarks("blue temple") == (None,)
    assert _landmarks(DegenerateTranslationError("cap")) == (None,)


def test_non_landmark_facts_are_untouched() -> None:
    facts = extract_facts(TEXT, "en")
    done = localize_landmarks(facts, "en", "kn", Fixed("ನೀಲಿ ದೇವಸ್ಥಾನ"))
    assert [f.local for f in done if f.kind != "landmark"] == [None] * (len(done) - 1)
