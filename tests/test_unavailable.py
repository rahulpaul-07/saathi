import pytest

from saathi.languages import LANGUAGES
from saathi.unavailable import UNAVAILABLE, unavailable_text


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_every_language_has_a_message(language: str) -> None:
    assert unavailable_text(language).strip()
    assert UNAVAILABLE[language].review_status == ("source" if language == "en" else "pending")


def test_table_has_no_extra_languages() -> None:
    assert set(UNAVAILABLE) == set(LANGUAGES)


def test_unknown_language_falls_back_to_english() -> None:
    assert unavailable_text("ur") == UNAVAILABLE["en"].text
