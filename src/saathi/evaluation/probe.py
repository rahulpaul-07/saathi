"""Day-one probe: how Gnani STT writes numbers and English words in Kannada and English output.

The fact extractor depends on this (digits? Kannada number words? transliterated English?), so it
is measured before the extractor is written. The utterances are synthetic addresses, read by
Gnani TTS: the probe shows the *form* of the transcript, not accuracy on real code-mixed speech.
"""

import re
from dataclasses import dataclass

# Kannada number words (cardinals and ordinal stems) as Gnani might write them.
_KANNADA_NUMBER_STEMS = (
    "ಒಂದ",
    "ಎರಡ",
    "ಮೂರ",
    "ನಾಲ್ಕ",
    "ಐದ",
    "ಆರ",
    "ಏಳ",
    "ಎಂಟ",
    "ಒಂಬತ್ತ",
    "ಹತ್ತ",
)
_TOKEN = re.compile(r"[^\s,.;:!?।]+")
_LATIN = re.compile(r"[A-Za-z]")
_KANNADA = re.compile(r"[ಀ-೿]")


@dataclass(frozen=True)
class ProbeText:
    key: str
    text: str
    tts_language: str  # Gnani language code used to speak it
    stt_languages: tuple[str, ...]  # codes the audio is transcribed with


def classify_token(token: str) -> str:
    """One of: digits, latin, kannada-number-word, kannada, other."""
    if any(ch.isdigit() for ch in token):
        return "digits"
    if _LATIN.search(token):
        return "latin"
    if _KANNADA.search(token):
        if token.startswith(_KANNADA_NUMBER_STEMS):
            return "kannada-number-word"
        return "kannada"
    return "other"


def classify_transcript(transcript: str) -> dict[str, list[str]]:
    """Group the transcript's tokens by how they are written (kannada tokens are left out)."""
    groups: dict[str, list[str]] = {"digits": [], "latin": [], "kannada-number-word": []}
    for token in _TOKEN.findall(transcript):
        kind = classify_token(token)
        if kind in groups:
            groups[kind].append(token)
    return groups


KN, EN = "kn-IN", "en-IN"
# Invented addresses (no real place). The Kannada mix writes some English words in Latin script
# (to see how TTS reads them) and some as Kannada transliteration (to see how STT writes them).
PROBE_TEXTS: tuple[ProbeText, ...] = (
    ProbeText(
        "kn-mix-latin-digits",
        "ನಮ್ಮ ಮನೆ 2nd cross, 3rd main, gate number 2 ಹತ್ತಿರ, opposite Ganesha temple",
        KN,
        (KN, EN),
    ),
    ProbeText(
        "kn-mix-floor-flat",
        "ಬ್ಲೂ ಬಿಲ್ಡಿಂಗ್, third floor, flat 304, ಲಿಫ್ಟ್ ಇಲ್ಲ",
        KN,
        (KN, EN),
    ),
    ProbeText(
        "kn-translit-words",
        "ಟವರ್ ಬಿ, ಬ್ಲಾಕ್ ಫೋರ್, ಗೇಟ್ ನಂಬರ್ ಎರಡು ಹತ್ತಿರ ಬನ್ನಿ",
        KN,
        (KN, EN),
    ),
    ProbeText(
        "kn-native-ordinals",
        "ಎರಡನೇ ಕ್ರಾಸ್, ಮೂರನೇ ಮೇನ್, ಗಣೇಶ ದೇವಸ್ಥಾನದ ಎದುರು",
        KN,
        (KN, EN),
    ),
    ProbeText(
        "kn-mix-house-number",
        "ಸೈಕಲ್ ಅಂಗಡಿ ಪಕ್ಕ ಲೆಫ್ಟ್ ತಗೊಳ್ಳಿ, house number 14, ಹಸಿರು ಗೇಟ್",
        KN,
        (KN, EN),
    ),
    ProbeText(
        "kn-mix-apartment",
        "ಅಪಾರ್ಟ್‌ಮೆಂಟ್ ಹೆಸರು Sunrise Residency, ಫ್ಲಾಟ್ 5B, ಎರಡನೇ ಮಹಡಿ",
        KN,
        (KN, EN),
    ),
    ProbeText(
        "en-cross-main",
        "Second cross, third main, gate number 2, opposite the Ganesha temple.",
        EN,
        (EN,),
    ),
    ProbeText(
        "en-block-flat",
        "Block C, flat 402, fourth floor, near the blue building.",
        EN,
        (EN,),
    ),
)

TTS_CALLS = len(PROBE_TEXTS)
STT_CALLS = sum(len(item.stt_languages) for item in PROBE_TEXTS)
PLANNED_PROBE_CALLS = TTS_CALLS + STT_CALLS
PROBE_CALL_CAP = PLANNED_PROBE_CALLS + 4  # room for a few rate-limit retries, counted
