"""The English text in the pages and scripts equals the source table, and every id is used."""

import json
import re
from pathlib import Path

import pytest

from saathi.chrome import ENGLISH

STATIC = Path(__file__).resolve().parent.parent / "src" / "saathi" / "static"
PAGES = ("customer.html", "rider.html")
TEXT_ATTR = re.compile(r'data-i18n="(\w+)"[^>]*>(.*?)</', re.DOTALL)
ARIA_ATTR = re.compile(r'aria-label="([^"]*)"[^>]*data-i18n-aria-label="(\w+)"')
JS_LOOKUP = re.compile(
    r'(?:\btb?\(|key: )\s*"(\w+)",\s*(?:english: )?"((?:[^"\\]|\\.)*)"', re.DOTALL
)


def squash(text: str) -> str:
    return " ".join(text.split())


def js_lookups() -> list[tuple[str, str, str]]:
    found = []
    for path in sorted((STATIC / "js").glob("*.js")):
        for key, english in JS_LOOKUP.findall(path.read_text(encoding="utf-8")):
            found.append((path.name, key, json.loads(f'"{english}"')))
    return found


def page_lookups() -> list[tuple[str, str, str]]:
    found = []
    for name in PAGES:
        html = (STATIC / name).read_text(encoding="utf-8")
        found += [(name, key, squash(text)) for key, text in TEXT_ATTR.findall(html)]
        found += [(name, key, aria) for aria, key in ARIA_ATTR.findall(html)]
    return found


@pytest.mark.parametrize("source", ["pages", "scripts"])
def test_the_english_in_the_code_is_the_table_text(source: str) -> None:
    lookups = page_lookups() if source == "pages" else js_lookups()
    assert lookups
    wrong = [
        (where, key)
        for where, key, english in lookups
        if key not in ENGLISH or squash(english) != ENGLISH[key]
    ]
    assert wrong == []


def test_every_string_id_is_used_by_a_page_or_a_script() -> None:
    used = {key for _, key, _ in page_lookups() + js_lookups()}
    assert sorted(set(ENGLISH) - used) == []


def test_pages_have_no_unmarked_visible_text() -> None:
    # Static text between tags must carry data-i18n, apart from the room code and link slots.
    for name in PAGES:
        html = (STATIC / name).read_text(encoding="utf-8")
        body = html.split("<body>")[1]
        for match in re.finditer(r"<(h1|h2|label|button|p|span)\b([^>]*)>([^<]+)</", body):
            tag, attrs, text = match.groups()
            if not text.strip() or "data-i18n" in attrs:
                continue
            raise AssertionError(f"{name}: <{tag}> text without data-i18n: {squash(text)!r}")
