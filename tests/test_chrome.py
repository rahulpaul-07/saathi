"""The interface text table: complete, in each language's own script, honestly labelled."""

import json
import re
from pathlib import Path

from saathi.chrome import CHROME, ENGLISH, SOURCE, word_overlap
from saathi.chrome_overrides import OVERRIDES
from saathi.languages import LANGUAGES
from saathi.quickreplies import QUICK_REPLIES
from saathi.repeatprompts import REPEAT_PROMPTS
from saathi.unavailable import TRANSLATION_UNAVAILABLE, UNAVAILABLE

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


def test_the_drift_report_covers_every_string_still_machine_made() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    # Hand-written overrides are not machine output, so the back-translation report skips them.
    pending = {
        (code, key)
        for code, strings in CHROME.items()
        for key, phrase in strings.items()
        if phrase.review_status == "pending" and key not in OVERRIDES.get(code, {})
    }
    assert {(row["lang"], row["key"]) for row in report["rows"]} == pending
    assert report["strings"] == len(pending)
    assert report["flagged"] == sum(1 for row in report["rows"] if row["flagged"])


def test_bn_and_hi_are_reviewed_and_use_the_agreed_words_for_rider_and_room() -> None:
    forbidden = {
        "hi": ("सवार", "कमर", "कक्ष"),
        "bn": ("আরোহী", "ঘর", "কক্ষ"),
    }
    for code, words in forbidden.items():
        # A string added after the review (a hand-written override) stays "pending" until the author
        # has read it; it is the only kind allowed to differ.
        statuses = {p.review_status for k, p in CHROME[code].items() if k not in OVERRIDES[code]}
        assert statuses == {"reviewed"}, code
        bad = [k for k, p in CHROME[code].items() if any(w in p.text for w in words)]
        assert bad == [], code
    assert CHROME["hi"]["role_rider"].text == "राइडर"
    assert "रूम" in CHROME["hi"]["room"].text and "রুম" in CHROME["bn"]["room"].text


# Words that mean a horse rider, a driver or a physical room; the app uses the English loanwords.
BANNED_STEMS = {
    "bn": ("আরোহী", "ঘর", "কক্ষ"),
    "gu": ("સવારી", "ખંડ", "ઓરડ"),
    "hi": ("सवार", "कमर", "कक्ष"),
    "kn": ("ಸವಾರ", "ಕೋಣೆ", "ಕೊಠಡಿ"),
    "ml": ("മുറി", "സവാരി"),
    "mr": ("स्वार", "चालक", "खोली", "कक्ष"),
    "pa": ("ਸਵਾਰ", "ਕਮਰ"),
    "ta": ("சவாரி", "அறை"),
    "te": ("సవారీ", "గది"),
}
RIDER_LOANWORD = {
    "bn": "রাইডার",
    "gu": "રાઇડર",
    "hi": "राइडर",
    "kn": "ರೈಡರ್",
    "ml": "റൈഡർ",
    "mr": "रायडर",
    "pa": "ਰਾਈਡਰ",
    "ta": "ரைடர்",
    "te": "రైడర్",
}
ROOM_LOANWORD = {
    "bn": "রুম",
    "gu": "રૂમ",
    "hi": "रूम",
    "kn": "ರೂಮ್",
    "ml": "റൂം",
    "mr": "रूम",
    "pa": "ਰੂਮ",
    "ta": "ரூம்",
    "te": "రూమ్",
}


def test_no_language_uses_a_horse_rider_or_physical_room_word_in_the_interface() -> None:
    assert set(BANNED_STEMS) == set(LANGUAGES) - {SOURCE}
    bad = [
        (code, key)
        for code, words in BANNED_STEMS.items()
        for key, phrase in CHROME[code].items()
        if any(w in phrase.text for w in words)
    ]
    assert bad == []


def test_no_language_uses_a_banned_word_in_the_other_phrase_tables() -> None:
    tables = [UNAVAILABLE, TRANSLATION_UNAVAILABLE]
    bad: list[tuple[str, str]] = []
    for code, words in BANNED_STEMS.items():
        for table in tables:
            if code in table and any(w in table[code].text for w in words):
                bad.append((code, table[code].text))
        phrases = [by_lang[code] for by_lang in QUICK_REPLIES.values() if code in by_lang]
        phrases += [by_lang[code] for by_lang in REPEAT_PROMPTS.values() if code in by_lang]
        bad += [(code, p.text) for p in phrases if any(w in p.text for w in words)]
    assert bad == []


def test_every_language_names_the_rider_and_the_room_with_the_loanwords() -> None:
    for code, word in RIDER_LOANWORD.items():
        assert word in CHROME[code]["role_rider"].text, code
    for code, word in ROOM_LOANWORD.items():
        assert word in CHROME[code]["room"].text, code


def test_https_and_localhost_stay_in_latin_in_the_microphone_message() -> None:
    for code in ("bn", "hi"):
        text = CHROME[code]["mic_secure_page"].text
        assert "HTTPS" in text and "localhost" in text, code


def test_word_overlap_flags_a_lost_meaning() -> None:
    assert word_overlap("Tap Repeat to hear it.", "Tap Repeat to hear it") == 1.0
    assert word_overlap("Come to the gate", "Bring the cake") < 0.5
