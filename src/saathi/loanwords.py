"""English address words that stay as transliterations in every language.

Indian speakers say "second cross, third main, gate number 2, opposite the temple" in English
words whatever language surrounds them, and a rider reads the same words the same way. A
translation model renders them as dictionary words ("opposite" -> "related", "main" ->
"principal"), so masking (`saathi.masking`) lifts them out of the text and puts back the spelling
below, in the listener's script.

One table, one row per word, one column per language; the first spelling in a cell is what is
written, the others are variants recognised in a transcript. The Latin English word is always
recognised, in any source language. These spellings were written by hand from general knowledge of
each language and are NOT reviewed by a speaker (bn and hi: the author may review; the beta
languages gu, ml, mr, pa, ta most likely carry mistakes). A wrong spelling here is spoken to a
rider, so reviews belong in docs/HANDOFF.md before any claim of quality.
"""

from saathi.facts.text import key
from saathi.languages import LANGUAGES

ENGLISH = "en"

# concept -> language -> "written variant variant ..."
_FORMS: dict[str, dict[str, str]] = {
    "cross": {
        "en": "cross", "kn": "ಕ್ರಾಸ್ ಕ್ರಾಸ", "hi": "क्रॉस क्रास", "bn": "ক্রস", "te": "క్రాస్",
        "gu": "ક્રોસ", "ml": "ക്രോസ്", "mr": "क्रॉस क्रास", "pa": "ਕਰਾਸ", "ta": "கிராஸ்",
    },
    "main": {
        "en": "main", "kn": "ಮೇನ್ ಮೈನ್", "hi": "मेन", "bn": "মেইন মেন", "te": "మెయిన్",
        "gu": "મેઇન", "ml": "മെയിൻ", "mr": "मेन", "pa": "ਮੇਨ", "ta": "மெயின்",
    },
    "gate": {
        "en": "gate", "kn": "ಗೇಟ್ ಗೇಟು", "hi": "गेट", "bn": "গেট", "te": "గేట్",
        "gu": "ગેટ", "ml": "ഗേറ്റ്", "mr": "गेट", "pa": "ਗੇਟ", "ta": "கேட்",
    },
    "floor": {
        "en": "floor", "kn": "ಫ್ಲೋರ್", "hi": "फ्लोर", "bn": "ফ্লোর", "te": "ఫ్లోర్",
        "gu": "ફ્લોર", "ml": "ഫ്ലോർ", "mr": "फ्लोअर फ्लोर", "pa": "ਫਲੋਰ", "ta": "ஃப்ளோர்",
    },
    "opposite": {
        "en": "opposite", "kn": "ಆಪೋಸಿಟ್ ಅಪೋಸಿಟ್", "hi": "ऑपोजिट ओपोजिट ओपोसिट ऑपोसिट",
        "bn": "অপোজিট", "te": "అపోజిట్", "gu": "ઓપોઝિટ", "ml": "ഓപ്പോസിറ്റ്",
        "mr": "ऑपोझिट अपोझिट", "pa": "ਆਪੋਜ਼ਿਟ", "ta": "ஆப்போசிட்",
    },
    "block": {
        "en": "block", "kn": "ಬ್ಲಾಕ್", "hi": "ब्लॉक ब्लाक", "bn": "ব্লক", "te": "బ్లాక్",
        "gu": "બ્લોક", "ml": "ബ്ലോക്ക്", "mr": "ब्लॉक ब्लाक", "pa": "ਬਲਾਕ", "ta": "பிளாக்",
    },
    "flat": {
        "en": "flat", "kn": "ಫ್ಲಾಟ್ ಫ್ಲ್ಯಾಟ್", "hi": "फ्लैट फ्लेट", "bn": "ফ্ল্যাট ফ্লাট",
        "te": "ఫ్లాట్", "gu": "ફ્લેટ", "ml": "ഫ്ലാറ്റ്", "mr": "फ्लॅट फ्लैट", "pa": "ਫਲੈਟ",
        "ta": "ஃபிளாட்",
    },
    "tower": {
        "en": "tower", "kn": "ಟವರ್", "hi": "टावर टॉवर", "bn": "টাওয়ার", "te": "టవర్",
        "gu": "ટાવર", "ml": "ടവർ", "mr": "टॉवर टावर", "pa": "ਟਾਵਰ", "ta": "டவர்",
    },
    "lift": {
        "en": "lift", "kn": "ಲಿಫ್ಟ್", "hi": "लिफ्ट", "bn": "লিফট", "te": "లిఫ్ట్",
        "gu": "લિફ્ટ", "ml": "ലിഫ്റ്റ്", "mr": "लिफ्ट", "pa": "ਲਿਫਟ", "ta": "லிஃப்ட்",
    },
    "apartment": {
        "en": "apartment", "kn": "ಅಪಾರ್ಟ್‌ಮೆಂಟ್ ಅಪಾರ್ಟ್ಮೆಂಟ್", "hi": "अपार्टमेंट",
        "bn": "অ্যাপার্টমেন্ট অ্যাপার্টমেন্ট", "te": "అపార్ట్మెంట్", "gu": "એપાર્ટમેન્ટ",
        "ml": "അപ്പാർട്ട്മെന്റ്", "mr": "अपार्टमेंट", "pa": "ਅਪਾਰਟਮੈਂਟ", "ta": "அபார்ட்மெண்ட்",
    },
    # Not an address word the speaker says: the class label of a chip or of the spoken fact summary.
    "landmark": {
        "en": "landmark", "kn": "ಲ್ಯಾಂಡ್‌ಮಾರ್ಕ್", "hi": "लैंडमार्क", "bn": "ল্যান্ডমার্ক",
        "te": "ల్యాండ్‌మార్క్", "gu": "લેન્ડમાર્ક", "ml": "ലാൻഡ്മാർക്ക്", "mr": "लँडमार्क",
        "pa": "ਲੈਂਡਮਾਰਕ", "ta": "லேண்ட்மார்க்",
    },
}  # fmt: skip

CONCEPTS: tuple[str, ...] = tuple(_FORMS)
# Concepts a speaker says inside a sentence; "landmark" is only a label and is never masked.
SPOKEN_CONCEPTS: frozenset[str] = frozenset(CONCEPTS) - {"landmark"}


def written(concept: str, language: str) -> str:
    """The spelling of `concept` in `language`'s script (KeyError for an unknown concept)."""
    return _FORMS[concept][language].split()[0]


def _recognised() -> dict[str, dict[str, str]]:
    """language -> normalised spelling -> concept, built once; English words count everywhere."""
    english = {
        key(form): concept for concept, row in _FORMS.items() for form in row[ENGLISH].split()
    }
    by_language: dict[str, dict[str, str]] = {}
    for language in LANGUAGES:
        forms = dict(english)
        for concept, row in _FORMS.items():
            if concept in SPOKEN_CONCEPTS:
                forms.update({key(form): concept for form in row[language].split()})
        by_language[language] = forms
    return by_language


_RECOGNISED = _recognised()


def concept_of(token_key: str, language: str) -> str | None:
    """The spoken concept a normalised token spells in a `language` transcript, if any."""
    concept = _RECOGNISED[language].get(token_key)
    return concept if concept in SPOKEN_CONCEPTS else None
