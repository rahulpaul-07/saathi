"""Each language's name as written in each viewer's script, for "the other person speaks X".

A Hindi page names Kannada "कन्नड़" (with the English name beside it, added by the page), not in
Kannada script that a Hindi reader may not know. Viewer language first, then the named language.
These are machine-assisted spellings of common language names, not yet checked by a native reader.
"""

ORDER = ("bn", "en", "hi", "kn", "te", "gu", "ml", "mr", "pa", "ta")

_ROWS: dict[str, tuple[str, ...]] = {
    "bn": (
        "বাংলা", "ইংরেজি", "হিন্দি", "কন্নড়", "তেলুগু",
        "গুজরাটি", "মালয়ালম", "মারাঠি", "পাঞ্জাবি", "তামিল",
    ),
    "en": (
        "Bengali", "English", "Hindi", "Kannada", "Telugu",
        "Gujarati", "Malayalam", "Marathi", "Punjabi", "Tamil",
    ),
    "hi": ("बंगाली", "अंग्रेज़ी", "हिन्दी", "कन्नड़", "तेलुगु", "गुजराती", "मलयालम", "मराठी", "पंजाबी", "तमिल"),
    "kn": ("ಬಂಗಾಳಿ", "ಇಂಗ್ಲಿಷ್", "ಹಿಂದಿ", "ಕನ್ನಡ", "ತೆಲುಗು", "ಗುಜರಾತಿ", "ಮಲಯಾಳಂ", "ಮರಾಠಿ", "ಪಂಜಾಬಿ", "ತಮಿಳು"),
    "te": ("బెంగాలీ", "ఇంగ్లీష్", "హిందీ", "కన్నడ", "తెలుగు", "గుజరాతీ", "మలయాళం", "మరాఠీ", "పంజాబీ", "తమిళం"),
    "gu": ("બંગાળી", "અંગ્રેજી", "હિન્દી", "કન્નડ", "તેલુગુ", "ગુજરાતી", "મલયાલમ", "મરાઠી", "પંજાબી", "તમિલ"),
    "ml": ("ബംഗാളി", "ഇംഗ്ലീഷ്", "ഹിന്ദി", "കന്നഡ", "തെലുങ്ക്", "ഗുജറാത്തി", "മലയാളം", "മറാഠി", "പഞ്ചാബി", "തമിഴ്"),
    "mr": ("बंगाली", "इंग्रजी", "हिंदी", "कन्नड", "तेलुगू", "गुजराती", "मलयाळम", "मराठी", "पंजाबी", "तमिळ"),
    "pa": ("ਬੰਗਾਲੀ", "ਅੰਗਰੇਜ਼ੀ", "ਹਿੰਦੀ", "ਕੰਨੜ", "ਤੇਲਗੂ", "ਗੁਜਰਾਤੀ", "ਮਲਿਆਲਮ", "ਮਰਾਠੀ", "ਪੰਜਾਬੀ", "ਤਮਿਲ"),
    "ta": (
        "வங்காளம்", "ஆங்கிலம்", "இந்தி", "கன்னடம்", "தெலுங்கு",
        "குஜராத்தி", "மலையாளம்", "மராத்தி", "பஞ்சாபி", "தமிழ்",
    ),
}

# viewer language -> named language -> its name in the viewer's script
LANGUAGE_NAMES: dict[str, dict[str, str]] = {
    viewer: dict(zip(ORDER, names, strict=True)) for viewer, names in _ROWS.items()
}


def names_of(code: str) -> dict[str, str]:
    """The name of `code` in each viewer's script, keyed by viewer language."""
    return {viewer: names[code] for viewer, names in LANGUAGE_NAMES.items()}
