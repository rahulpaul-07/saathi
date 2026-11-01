"""Shown to the SPEAKER, in their own language, when a stage of the turn failed on our side: the
speech service (even after a retry) or the translator. Fixed text, never translated at runtime.
Every text except English is unreviewed machine output written for these tables ("pending"); the
status travels with the text so the UI can say so. Nothing here is tied to a role.
"""

from saathi.quickreplies import Phrase

UNAVAILABLE: dict[str, Phrase] = {
    "en": Phrase("The speech service is not responding. Please try again.", "source"),
    "bn": Phrase("স্পিচ সার্ভিস সাড়া দিচ্ছে না। আবার চেষ্টা করুন।", "pending"),
    "hi": Phrase("स्पीच सेवा जवाब नहीं दे रही। कृपया फिर से कोशिश करें।", "pending"),
    "kn": Phrase("ಸ್ಪೀಚ್ ಸೇವೆ ಪ್ರತಿಕ್ರಿಯಿಸುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.", "pending"),
    "te": Phrase("స్పీచ్ సేవ స్పందించడం లేదు. దయచేసి మళ్ళీ ప్రయత్నించండి.", "pending"),
    "gu": Phrase("સ્પીચ સેવા જવાબ આપી રહી નથી. મહેરબાની કરીને ફરી પ્રયાસ કરો.", "pending"),
    "ml": Phrase("സ്പീച്ച് സേവനം പ്രതികരിക്കുന്നില്ല. ദയവായി വീണ്ടും ശ്രമിക്കുക.", "pending"),
    "mr": Phrase("स्पीच सेवा प्रतिसाद देत नाही. कृपया पुन्हा प्रयत्न करा.", "pending"),
    "pa": Phrase("ਸਪੀਚ ਸੇਵਾ ਜਵਾਬ ਨਹੀਂ ਦੇ ਰਹੀ। ਕ੍ਰਿਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।", "pending"),
    "ta": Phrase("பேச்சு சேவை பதிலளிக்கவில்லை. தயவுசெய்து மீண்டும் முயற்சிக்கவும்.", "pending"),
}

TRANSLATION_UNAVAILABLE: dict[str, Phrase] = {
    "en": Phrase("Translation is not working right now. Please try again.", "source"),
    "bn": Phrase("এখন অনুবাদ কাজ করছে না। আবার চেষ্টা করুন।", "pending"),
    "hi": Phrase("अनुवाद अभी काम नहीं कर रहा। कृपया फिर से कोशिश करें।", "pending"),
    "kn": Phrase("ಅನುವಾದ ಈಗ ಕೆಲಸ ಮಾಡುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.", "pending"),
    "te": Phrase("అనువాదం ఇప్పుడు పనిచేయడం లేదు. దయచేసి మళ్ళీ ప్రయత్నించండి.", "pending"),
    "gu": Phrase("અનુવાદ હમણાં કામ કરતો નથી. મહેરબાની કરીને ફરી પ્રયાસ કરો.", "pending"),
    "ml": Phrase("വിവർത്തനം ഇപ്പോൾ പ്രവർത്തിക്കുന്നില്ല. ദയവായി വീണ്ടും ശ്രമിക്കുക.", "pending"),
    "mr": Phrase("भाषांतर आत्ता काम करत नाही. कृपया पुन्हा प्रयत्न करा.", "pending"),
    "pa": Phrase("ਅਨੁਵਾਦ ਹੁਣ ਕੰਮ ਨਹੀਂ ਕਰ ਰਿਹਾ। ਕ੍ਰਿਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।", "pending"),
    "ta": Phrase("மொழிபெயர்ப்பு இப்போது வேலை செய்யவில்லை. தயவுசெய்து மீண்டும் முயற்சிக்கவும்.", "pending"),
}


def unavailable_text(language: str) -> str:
    """The message in `language`, falling back to English for a language with no entry."""
    return UNAVAILABLE.get(language, UNAVAILABLE["en"]).text


def translation_unavailable_text(language: str) -> str:
    return TRANSLATION_UNAVAILABLE.get(language, TRANSLATION_UNAVAILABLE["en"]).text
