"""Extraction data for the languages with native rules, and the English universal layer.

Native number words, trigger words and spelling variants were written from the day-one probe
(docs/DECISIONS.md, "Probe findings") and general knowledge of each language; they are NOT
validated against real STT output of speakers. Anything not listed is simply not found.
Tamil and Telugu live in lexicons_ta_te.py and were built from real STT output instead.
"""

from saathi.facts.lexicon import Lexicon, merge, phrases, same, table, trigger_map, words
from saathi.facts.lexicons_gu_ml_mr_pa import GU, ML, MR, PA
from saathi.facts.lexicons_ta_te import TA, TE
from saathi.facts.text import key

_NONE: frozenset[tuple[str, ...]] = frozenset()


def _tens(spec: str) -> dict[str, int]:
    """Twenty, thirty, ...: consecutive tens starting at 20."""
    return {key(word): (index + 2) * 10 for index, word in enumerate(spec.split())}


def _letters(spec: str) -> dict[str, str]:
    """Spoken names of the letters A to F."""
    return {key(name): letter for name, letter in zip(spec.split(), "ABCDEF", strict=True)}


# --- English: the universal layer (digits are language independent, see numbers.py) ------------

EN = Lexicon(
    numbers=table(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen"
    )
    | _tens("twenty thirty forty fifty sixty seventy eighty ninety")
    | {key("hundred"): 100},
    ordinals=table(
        "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth "
        "thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth",
        start=1,
    ),
    hundred_words=words("hundred"),
    hundred_joiners=words("and"),
    spaced_tens=True,
    ordinal_suffix_tokens=frozenset(),
    digit_ordinal_suffixes=words("st nd rd th"),
    fillers=words("number no num nr nos"),
    letters={},  # Latin letters are read directly, see numbers.parse_letter
    triggers=trigger_map(
        gate="gate",
        floor="floor storey",
        cross="cross",
        main="main",
        block="block tower wing",
        flat="flat house",
    ),
    landmark_before=phrases(
        "opposite|opposite to|near|beside|behind|next to|in front of|adjacent to|across from"
    ),
    landmark_after=_NONE,
    stopwords=words(
        "my our house is it and then take turn left right go come straight you will find at on "
        "in there here from i am"
    ),
    leading_particles=words("the a an to of"),
    trailing_particles=frozenset(),
)

# --- Kannada ----------------------------------------------------------------------------------

_KN_UNITS = "ಒಂದು ಎರಡು ಮೂರು ನಾಲ್ಕು ಐದು ಆರು ಏಳು ಎಂಟು ಒಂಬತ್ತು".split()
_KN_TEENS = ("ಹತ್ತು ಹನ್ನೊಂದು ಹನ್ನೆರಡು ಹದಿಮೂರು ಹದಿನಾಲ್ಕು ಹದಿನೈದು ಹದಿನಾರು ಹದಿನೇಳು ಹದಿನೆಂಟು ಹತ್ತೊಂಬತ್ತು").split()
_KN_TENS = "ಇಪ್ಪತ್ತು ಮೂವತ್ತು ನಲವತ್ತು ಐವತ್ತು ಅರವತ್ತು ಎಪ್ಪತ್ತು ಎಂಬತ್ತು ತೊಂಬತ್ತು".split()
# Independent vowel -> dependent vowel sign, needed when a unit joins a tens word (sandhi).
_KN_VOWEL_SIGN = {
    "ಆ": "ಾ", "ಇ": "ಿ", "ಈ": "ೀ", "ಉ": "ು", "ಊ": "ೂ",
    "ಎ": "ೆ", "ಏ": "ೇ", "ಐ": "ೈ", "ಒ": "ೊ", "ಓ": "ೋ", "ಔ": "ೌ",
}  # fmt: skip
_KN_HUNDREDS = {
    100: "ನೂರ", 200: "ಇನ್ನೂರ", 300: "ಮುನ್ನೂರ", 400: "ನಾನೂರ", 500: "ಐನೂರ",
    600: "ಆರುನೂರ", 700: "ಏಳುನೂರ", 800: "ಎಂಟುನೂರ", 900: "ಒಂಬೈನೂರ",
}  # fmt: skip
_KN_U = "ು"


def _kn_compound(tens_word: str, unit_word: str) -> str:
    """ಇಪ್ಪತ್ತು + ಒಂದು -> ಇಪ್ಪತ್ತೊಂದು: drop the tens' final vowel, then join with sandhi."""
    first = unit_word[0]
    return tens_word.removesuffix(_KN_U) + _KN_VOWEL_SIGN.get(first, first) + unit_word[1:]


def _kn_native_numbers() -> dict[str, int]:
    """Native Kannada cardinals 1-99 (every word ends in -u), keyed by surface form."""
    numbers = {word: value for value, word in enumerate(_KN_UNITS, start=1)}
    numbers |= {word: value for value, word in enumerate(_KN_TEENS, start=10)}
    for tens_index, tens_word in enumerate(_KN_TENS):
        tens_value = (tens_index + 2) * 10
        numbers[tens_word] = tens_value
        for unit_value, unit_word in enumerate(_KN_UNITS, start=1):
            numbers[_kn_compound(tens_word, unit_word)] = tens_value + unit_value
    return numbers


def _kn_lexicon() -> Lexicon:
    native = _kn_native_numbers()
    numbers = {key(word): value for word, value in native.items()}
    numbers |= {key("ಸೊನ್ನೆ"): 0, key("ಶೂನ್ಯ"): 0}
    for value, stem in _KN_HUNDREDS.items():  # "ಮುನ್ನೂರ ನಾಲ್ಕು" (probe): the oblique stem
        numbers[key(stem)] = value
        numbers[key(stem + _KN_U)] = value
    # English number words transliterated: how STT writes "gate number two" in Kannada.
    numbers |= table("ಒನ್ ಟು ತ್ರೀ ಫೋರ್ ಫೈವ್ ಸಿಕ್ಸ್ ಸೆವೆನ್ ಎಯ್ಟ್ ನೈನ್ ಟೆನ್", start=1)
    numbers[key("ಟೂ")] = 2
    # ಎರಡು -> ಎರಡನೇ: the ordinal is the cardinal stem plus -ನೇ (probe: ಎರಡನೇ, ಮೂರನೇ).
    ordinals = {key(word.removesuffix(_KN_U) + "ನೇ"): value for word, value in native.items()}
    ordinals |= {key("ಮೊದಲನೇ"): 1, key("ಮೊದಲ"): 1, key("ಫಸ್ಟ್"): 1, key("ಸೆಕೆಂಡ್"): 2}
    ordinals |= {key("ಥರ್ಡ್"): 3, key("ಫೋರ್ತ್"): 4, key("ಫಿಫ್ತ್"): 5}
    return Lexicon(
        numbers=numbers,
        ordinals=ordinals,
        hundred_words=words("ನೂರು ನೂರ"),
        hundred_joiners=frozenset(),
        spaced_tens=False,
        ordinal_suffix_tokens=words("ನೇ ನೆ"),  # probe: "ಎರಡು ನೇ"
        digit_ordinal_suffixes=words("ನೇ ನೆ"),
        fillers=words("ನಂಬರ್ ನಂಬರ ನಂ"),
        letters=_letters("ಎ ಬಿ ಸಿ ಡಿ ಇ ಎಫ್"),
        triggers=trigger_map(
            gate="ಗೇಟ್ ಗೇಟು",
            floor="ಫ್ಲೋರ್ ಮಹಡಿ",
            cross="ಕ್ರಾಸ್",
            main="ಮೇನ್ ಮೈನ್",
            block="ಬ್ಲಾಕ್ ಟವರ್",
            flat="ಫ್ಲಾಟ್ ಫ್ಲ್ಯಾಟ್ ಹೌಸ್",  # probe: both spellings of "flat" occur
        ),
        landmark_before=phrases("ಆಪೋಸಿಟ್|ಅಪೋಸಿಟ್|ನಿಯರ್|ಬಿಹೈಂಡ್|ನೆಕ್ಸ್ಟ್ ಟು"),
        landmark_after=phrases("ಎದುರು|ಎದುರಿಗೆ|ಹತ್ತಿರ|ಪಕ್ಕ|ಪಕ್ಕದಲ್ಲಿ|ಬಳಿ|ಸಮೀಪ|ಹಿಂದೆ|ಹಿಂಭಾಗದಲ್ಲಿ"),
        stopwords=words("ನಮ್ಮ ಮನೆ ಇದೆ ಬನ್ನಿ ತಗೊಳ್ಳಿ ಲೆಫ್ಟ್ ರೈಟ್ ಮತ್ತು ನಂತರ ಅಲ್ಲಿ ಇಲ್ಲಿ ನೇರ"),
        leading_particles=frozenset(),
        trailing_particles=frozenset(),
    )


KN = _kn_lexicon()

# --- Hindi ------------------------------------------------------------------------------------

_HI_TO_50 = table(
    "शून्य एक दो तीन चार पांच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस "
    "चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चौवालीस "
    "पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास"
)
# 51-99 as spoken. Every decade has its own irregular forms in Hindi, so each is listed.
_HI_51_TO_99 = table(
    "इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ "
    "इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर "
    "इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी "
    "इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे "
    "इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे",
    start=51,
)
_HI_ORDINAL_SUFFIXES = words("वां वीं वें वा वी वे")


def _hi_lexicon() -> Lexicon:
    numbers = dict(_HI_TO_50) | _HI_51_TO_99
    numbers |= {key("साठ"): 60, key("सत्तर"): 70, key("अस्सी"): 80, key("नब्बे"): 90, key("सौ"): 100}
    numbers |= {key("छः"): 6, key("पन्द्रह"): 15, key("अठाईस"): 28, key("चौतीस"): 34}
    numbers |= table("वन टू थ्री फोर फाइव सिक्स सेवन एट नाइन टेन", start=1)
    # Regular -वां ordinals (पांचवां, सातवां ... पचासवां); 1-4 and 6 are irregular.
    ordinals = {
        word + suffix: value
        for word, value in (_HI_TO_50 | _HI_51_TO_99).items()
        if value == 5 or 7 <= value <= 99
        for suffix in _HI_ORDINAL_SUFFIXES
    }
    ordinals |= same("पहला पहली पहले फर्स्ट", 1) | same("दूसरा दूसरी दूसरे सेकंड सेकेंड", 2)
    ordinals |= same("तीसरा तीसरी तीसरे थर्ड", 3) | same("चौथा चौथी चौथे फोर्थ", 4)
    ordinals |= same("पांचवां फिफ्थ", 5) | same("छठा छठी छठे", 6)
    return Lexicon(
        numbers=numbers,
        ordinals=ordinals,
        hundred_words=words("सौ"),
        hundred_joiners=frozenset(),
        spaced_tens=False,
        ordinal_suffix_tokens=frozenset(),
        digit_ordinal_suffixes=words("वां वीं वें वा वी वे रा री ला"),
        fillers=words("नंबर नम्बर नं"),
        letters=_letters("ए बी सी डी ई एफ"),
        triggers=trigger_map(
            gate="गेट",
            floor="फ्लोर मंजिल",
            cross="क्रॉस क्रास",
            main="मेन",
            block="ब्लॉक ब्लाक टावर टॉवर",
            flat="फ्लैट फ्लेट मकान",
        ),
        landmark_before=phrases("ओपोजिट|ऑपोजिट|ओपोसिट|नियर|बिहाइंड|नेक्स्ट टू"),
        landmark_after=phrases("सामने|पास|नजदीक|बगल|पीछे"),
        stopwords=words("मेरा मेरे मेरी घर है हैं और फिर आइए आना बाएं दाएं लेफ्ट राइट पर आप"),
        leading_particles=frozenset(),
        trailing_particles=words("के की का"),
    )


HI = _hi_lexicon()

# --- Bengali ----------------------------------------------------------------------------------

_BN_TO_50 = table(
    "শূন্য এক দুই তিন চার পাঁচ ছয় সাত আট নয় দশ এগারো বারো তেরো চৌদ্দ পনেরো ষোলো সতেরো আঠারো ঊনিশ "
    "কুড়ি একুশ বাইশ তেইশ চব্বিশ পঁচিশ ছাব্বিশ সাতাশ আটাশ ঊনত্রিশ ত্রিশ একত্রিশ বত্রিশ তেত্রিশ "
    "চৌত্রিশ পঁয়ত্রিশ ছত্রিশ সাঁইত্রিশ আটত্রিশ ঊনচল্লিশ চল্লিশ একচল্লিশ বিয়াল্লিশ তেতাল্লিশ "
    "চুয়াল্লিশ পঁয়তাল্লিশ ছেচল্লিশ সাতচল্লিশ আটচল্লিশ ঊনপঞ্চাশ পঞ্চাশ"
)
# 51-99 as spoken; the decades 60-90 are repeated in _bn_lexicon with their spelling variants.
_BN_51_TO_99 = table(
    "একান্ন বাহান্ন তিপ্পান্ন চুয়ান্ন পঞ্চান্ন ছাপ্পান্ন সাতান্ন আটান্ন ঊনষাট ষাট "
    "একষট্টি বাষট্টি তেষট্টি চৌষট্টি পঁয়ষট্টি ছেষট্টি সাতষট্টি আটষট্টি ঊনসত্তর সত্তর "
    "একাত্তর বাহাত্তর তিয়াত্তর চুয়াত্তর পঁচাত্তর ছিয়াত্তর সাতাত্তর আটাত্তর ঊনআশি আশি "
    "একাশি বিরাশি তিরাশি চুরাশি পঁচাশি ছিয়াশি সাতাশি অষ্টাশি ঊননব্বই নব্বই "
    "একানব্বই বিরানব্বই তিরানব্বই চুরানব্বই পঁচানব্বই ছিয়ানব্বই সাতানব্বই আটানব্বই নিরানব্বই",
    start=51,
)
_BN_UNIT_STEMS = ("এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়")


def _bn_lexicon() -> Lexicon:
    numbers = dict(_BN_TO_50) | _BN_51_TO_99
    numbers |= {key("বিশ"): 20, key("উনিশ"): 19, key("উনত্রিশ"): 29, key("চোদ্দ"): 14}
    numbers |= {key("ষাট"): 60, key("সত্তর"): 70, key("আশি"): 80, key("নব্বই"): 90}
    numbers |= {key("শো"): 100, key("শ"): 100, key("দুশো"): 200, key("দুশ"): 200}
    for value, stem in enumerate(_BN_UNIT_STEMS, start=1):  # তিনশো = 300
        numbers[key(stem + "শো")] = value * 100
        numbers[key(stem + "শ")] = value * 100
    numbers |= table("ওয়ান টু থ্রি ফোর ফাইভ সিক্স সেভেন এইট নাইন টেন", start=1)
    ordinals = table("প্রথম দ্বিতীয় তৃতীয় চতুর্থ পঞ্চম ষষ্ঠ সপ্তম অষ্টম নবম দশম", start=1)
    ordinals |= {key("ফার্স্ট"): 1, key("সেকেন্ড"): 2, key("থার্ড"): 3, key("ফোর্থ"): 4}
    return Lexicon(
        numbers=numbers,
        ordinals=ordinals,
        hundred_words=words("শো শ"),
        hundred_joiners=frozenset(),
        spaced_tens=False,
        ordinal_suffix_tokens=frozenset(),
        digit_ordinal_suffixes=words("য় ম র্থ ষ্ঠ তম"),  # "২০তম" is twentieth
        fillers=words("নম্বর নাম্বার নং"),
        letters=_letters("এ বি সি ডি ই এফ"),
        triggers=trigger_map(
            gate="গেট",
            floor="ফ্লোর ফ্লোরে তলা তলায়",
            cross="ক্রস",
            main="মেইন মেন",
            block="ব্লক টাওয়ার",
            flat="ফ্ল্যাট ফ্লাট",
        ),
        landmark_before=phrases("অপোজিট|নিয়ার"),
        landmark_after=phrases("সামনে|কাছে|পাশে|পিছনে|পেছনে|বিপরীতে"),
        stopwords=words("আমার বাড়ি বাসা আছে আর এবং তারপর বাঁয়ে ডানে লেফট রাইট এসো"),
        leading_particles=frozenset(),
        trailing_particles=frozenset(),
    )


BN = _bn_lexicon()

# Native layers by language code. A language missing here gets only the universal English layer
# (digits and English direction words), which is the stated limit for the non-core languages.
NATIVE: dict[str, Lexicon] = {
    "kn": KN, "hi": HI, "bn": BN, "ta": TA, "te": TE, "gu": GU, "ml": ML, "mr": MR, "pa": PA,
}  # fmt: skip


def lexicon_for(language: str) -> Lexicon:
    """The merged lexicon for a language code: English universal layer plus its native layer."""
    native = NATIVE.get(language)
    return EN if native is None or language == "en" else merge(EN, native)
