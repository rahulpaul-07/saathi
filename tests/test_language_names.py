"""Language names in each viewer's script, shown beside the English name."""

import re

from saathi.language_names import LANGUAGE_NAMES, ORDER, names_of
from saathi.languages import LANGUAGES
from test_chrome import SCRIPT


def test_every_language_has_a_name_for_every_viewer() -> None:
    assert set(LANGUAGE_NAMES) == set(LANGUAGES)
    for language in LANGUAGES:
        names = names_of(language)  # keyed by viewer
        assert set(names) == set(LANGUAGES), language
        assert all(name.strip() for name in names.values()), language


def test_names_are_in_the_viewers_script() -> None:
    wrong = [
        (viewer, language)
        for language in LANGUAGES
        for viewer, name in names_of(language).items()
        if viewer in SCRIPT and not re.search(SCRIPT[viewer], name)
    ]
    assert wrong == []


def test_english_viewer_gets_the_english_names() -> None:
    assert {code: names_of(code)["en"] for code in LANGUAGES} == {
        code: lang.name for code, lang in LANGUAGES.items()
    }


def test_a_language_is_named_on_its_own_page_as_its_native_name() -> None:
    for code, lang in LANGUAGES.items():
        assert names_of(code)[code] == lang.native, code


def test_the_order_covers_all_ten_once() -> None:
    assert sorted(ORDER) == sorted(LANGUAGES)
