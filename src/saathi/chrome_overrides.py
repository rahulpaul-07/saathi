"""Hand-written interface text that wins over the generated table in `chrome_data.py`.

`scripts/gen_chrome.py` regenerates every string that is not "reviewed"; an edit made by hand in
the generated file would be lost on the next run. Anything written or corrected by a person goes
here instead: the generator skips these keys and `saathi.chrome` applies them over the generated
data, so a stale or regenerated data file can never undo them. Status is "pending" until a native
speaker has checked that exact text, as everywhere else.
"""

from saathi.quickreplies import ReviewStatus

Table = dict[str, dict[str, tuple[str, ReviewStatus]]]

OVERRIDES: Table = {
    "bn": {"choose_a_clip": ("ক্লিপ বেছে নিন", "reviewed")},
    "gu": {"choose_a_clip": ("ક્લિપ પસંદ કરો", "pending")},
    "hi": {"choose_a_clip": ("क्लिप चुनें", "reviewed")},
    "kn": {"choose_a_clip": ("ಕ್ಲಿಪ್ ಆಯ್ಕೆಮಾಡಿ", "pending")},
    "ml": {"choose_a_clip": ("ക്ലിപ്പ് തിരഞ്ഞെടുക്കുക", "pending")},
    "mr": {"choose_a_clip": ("क्लिप निवडा", "pending")},
    "pa": {"choose_a_clip": ("ਕਲਿੱਪ ਚੁਣੋ", "pending")},
    "ta": {"choose_a_clip": ("கிளிப்பைத் தேர்ந்தெடுக்கவும்", "pending")},
    "te": {"choose_a_clip": ("క్లిప్ ఎంచుకోండి", "pending")},
}


def apply_overrides(table: Table, overrides: Table = OVERRIDES) -> Table:
    """A copy of `table` with every override in place; an override replaces the generated text."""
    merged = {code: dict(strings) for code, strings in table.items()}
    for code, strings in overrides.items():
        merged.setdefault(code, {}).update(strings)
    return merged
