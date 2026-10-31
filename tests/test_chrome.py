"""The interface text table: complete, in each language's own script, honestly labelled."""

import json
import re
from pathlib import Path

from saathi.chrome import CHROME, ENGLISH, SOURCE, word_overlap
from saathi.languages import LANGUAGES

SCRIPT = {
    "bn": r"[ঀ-৿]",
    "gu": r"[઀-૿]",
    "hi": r"[ऀ-ॿ]",
    "mr": r"[ऀ-ॿ]",
    "kn": r"[ಀ-೿]",
    "ml": r"[ഀ-ൿ]",
    "pa": r"[਀-੿]",
    "ta": r"[஀-௿]",
    "te": r"[ఀ-౿]",
}
REPORT = Path(__file__).resolve().parent.parent / "eval" / "results" / "chrome_backtranslation.json"


def test_every_key_exists_in_all_ten_languages() -> None:
    assert set(CHROME) == set(LANGUAGES)
    for code, strings in CHROME.items():
        assert set(strings) == set(ENGLISH), code
        assert all(phrase.text.strip() for phrase in strings.values()), code


def test_each_translation_is_written_in_its_own_script() -> None:
    missing = [
        (code, key)
        for code, pattern in SCRIPT.items()
        for key, phrase in CHROME[code].items()
        if not re.search(pattern, phrase.text)
    ]
    assert missing == []


def test_english_is_the_only_source_and_nothing_machine_made_claims_review() -> None:
    assert {p.review_status for p in CHROME[SOURCE].values()} == {"source"}
    for code, strings in CHROME.items():
        if code != SOURCE:
            assert {p.review_status for p in strings.values()} <= {"pending", "reviewed"}


def test_strings_carry_no_placeholders_or_markup() -> None:
    for code, strings in CHROME.items():
        for key, phrase in strings.items():
            assert not re.search(r"[{}<>]|\$\{", phrase.text), (code, key)


def test_no_translation_is_left_as_the_english_source() -> None:
    same = [
        (code, key)
        for code, strings in CHROME.items()
        if code != SOURCE
        for key, phrase in strings.items()
        if phrase.text == ENGLISH[key]
    ]
    assert same == []


def test_the_drift_report_covers_every_generated_string() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["strings"] == (len(LANGUAGES) - 1) * len(ENGLISH)
    assert report["flagged"] == sum(1 for row in report["rows"] if row["flagged"])


def test_word_overlap_flags_a_lost_meaning() -> None:
    assert word_overlap("Tap Repeat to hear it.", "Tap Repeat to hear it") == 1.0
    assert word_overlap("Come to the gate", "Bring the cake") < 0.5
