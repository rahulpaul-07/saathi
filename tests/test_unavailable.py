import pytest

from saathi.languages import LANGUAGES
from saathi.unavailable import (
    TRANSLATION_UNAVAILABLE,
    UNAVAILABLE,
    translation_unavailable_text,
    unavailable_text,
)


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_every_language_has_a_message(language: str) -> None:
    assert unavailable_text(language).strip()
    assert UNAVAILABLE[language].review_status == ("source" if language == "en" else "pending")


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_every_language_has_a_translation_failure_message(language: str) -> None:
    assert translation_unavailable_text(language).strip()
    status = TRANSLATION_UNAVAILABLE[language].review_status
    assert status == ("source" if language == "en" else "pending")


def test_the_two_messages_differ_in_every_language() -> None:
    for language in LANGUAGES:
        assert translation_unavailable_text(language) != unavailable_text(language)


def test_tables_have_no_extra_languages() -> None:
    assert set(UNAVAILABLE) == set(LANGUAGES)
    assert set(TRANSLATION_UNAVAILABLE) == set(LANGUAGES)


def test_unknown_language_falls_back_to_english() -> None:
    assert unavailable_text("ur") == UNAVAILABLE["en"].text
    assert translation_unavailable_text("ur") == TRANSLATION_UNAVAILABLE["en"].text
