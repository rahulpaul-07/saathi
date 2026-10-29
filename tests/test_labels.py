import pytest

from saathi.labels import KINDS, chip_label
from saathi.languages import LANGUAGES


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_every_kind_has_a_label_in_every_language(language: str) -> None:
    for kind in KINDS:
        assert chip_label(kind, language).text


def test_bn_uses_the_loanword_spellings_people_say() -> None:
    assert [chip_label(kind, "bn").text for kind in ("gate", "cross", "main")] == [
        "গেট",
        "ক্রস",
        "মেইন",
    ]


def test_reviewed_labels_come_from_reviewed_quick_replies_only() -> None:
    reviewed = {
        (kind, language)
        for kind in KINDS
        for language in LANGUAGES
        if chip_label(kind, language).status == "reviewed"
    }
    assert reviewed == {("gate", "bn"), ("floor", "bn"), ("gate", "hi"), ("floor", "hi")}


def test_english_is_the_source_and_everything_else_is_pending_or_reviewed() -> None:
    assert chip_label("gate", "en").status == "source"
    assert chip_label("landmark", "kn").status == "pending"
    assert chip_label("cross", "hi").status == "pending"


def test_unknown_kind_or_language_is_refused() -> None:
    with pytest.raises(KeyError):
        chip_label("sauce", "bn")
    with pytest.raises(KeyError):
        chip_label("gate", "xx")
