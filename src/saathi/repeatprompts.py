"""Please-repeat prompts: shown to the SPEAKER, in their own language, when a turn gave the
listener nothing reliable. Fixed text, never translated at runtime, no personal data.

Two reasons, one phrase each per language:
- "no_facts": no gate, floor, cross/main or landmark was found in what the CUSTOMER said. Riders
  are not asked: "coming in 2 minutes" has no address in it.
- "unverified": the translation failed the placeholder check, so the listener got a plain summary.

English is the source. bn and hi were rewritten and reviewed by the author ("reviewed"). The other
eight languages are unreviewed machine output from `scripts/gen_repeat_prompts.py` ("pending"); the
UI says so. Nothing here is tied to a role.
"""

from typing import Literal

from saathi.quickreplies import Phrase
from saathi.rooms import Role

RepeatReason = Literal["no_facts", "unverified"]

REPEAT_PROMPTS: dict[str, dict[RepeatReason, Phrase]] = {
    "en": {
        # No "gate" or "floor" here: the machine translator renders them as "door" and "ground".
        "no_facts": Phrase("No address details were found. Please repeat the address.", "source"),
        "unverified": Phrase(
            "The translation could not be checked. Please say it again, slowly.", "source"
        ),
    },
    "bn": {
        "no_facts": Phrase("কোনো ঠিকানার তথ্য পাওয়া যায়নি। ঠিকানাটা আবার বলুন।", "reviewed"),
        "unverified": Phrase("অনুবাদটা নিশ্চিত করা যায়নি। আরেকবার ধীরে ধীরে বলুন।", "reviewed"),
    },
    "hi": {
        "no_facts": Phrase("पते की जानकारी नहीं मिली। कृपया पता दोबारा बताइए।", "reviewed"),
        "unverified": Phrase("अनुवाद पक्का नहीं हो पाया। कृपया धीरे-धीरे दोबारा बोलिए।", "reviewed"),
    },
    "kn": {
        "no_facts": Phrase("ವಿಳಾಸದ ವಿವರಗಳು ಕಂಡುಬಂದಿಲ್ಲ. ದಯವಿಟ್ಟು ವಿಳಾಸವನ್ನು ಪುನರಾವರ್ತಿಸಿ.", "pending"),
        "unverified": Phrase(
            "ಅನುವಾದವನ್ನು ಪರಿಶೀಲಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಅದನ್ನು ನಿಧಾನವಾಗಿ ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ.",
            "pending",
        ),
    },
    "te": {
        "no_facts": Phrase("చిరునామా వివరాలు దొరకలేదు. దయచేసి చిరునామాను పునరావృతం చేయండి.", "pending"),
        "unverified": Phrase("అనువాదం తనిఖీ చేయబడలేదు. దయచేసి మళ్ళీ చెప్పండి, నెమ్మదిగా.", "pending"),
    },
    "gu": {
        "no_facts": Phrase(
            "સરનામાની કોઈ વિગતો મળી નથી. મહેરબાની કરીને સરનામાનું પુનરાવર્તન કરો.", "pending"
        ),
        "unverified": Phrase(
            "અનુવાદ ચકાસી શકાયો નથી. મહેરબાની કરીને તે ફરીથી કહો, ધીમે ધીમે.", "pending"
        ),
    },
    "ml": {
        "no_facts": Phrase(
            "വിലാസ വിശദാംശങ്ങളൊന്നും കണ്ടെത്തിയിട്ടില്ല. ദയവായി വിലാസം ആവർത്തിക്കുക.", "pending"
        ),
        "unverified": Phrase(
            "വിവർത്തനം പരിശോധിക്കാൻ കഴിഞ്ഞില്ല. ദയവായി പതുക്കെ വീണ്ടും പറയൂ.", "pending"
        ),
    },
    "mr": {
        "no_facts": Phrase("पत्त्याचा तपशील सापडला नाही. कृपया पत्ता पुन्हा करा.", "pending"),
        "unverified": Phrase("अनुवाद तपासणे शक्य झाले नाही. कृपया ते पुन्हा, हळूहळू सांगा.", "pending"),
    },
    "pa": {
        "no_facts": Phrase("ਕੋਈ ਪਤਾ ਵੇਰਵਾ ਨਹੀਂ ਮਿਲਿਆ। ਕ੍ਰਿਪਾ ਕਰਕੇ ਪਤਾ ਦੁਹਰਾਓ।", "pending"),
        "unverified": Phrase(
            "ਅਨੁਵਾਦ ਦੀ ਜਾਂਚ ਨਹੀਂ ਕੀਤੀ ਜਾ ਸਕੀ। ਕ੍ਰਿਪਾ ਕਰਕੇ ਹੌਲੀ-ਹੌਲੀ ਇਸ ਨੂੰ ਦੁਬਾਰਾ ਕਹੋ।", "pending"
        ),
    },
    "ta": {
        "no_facts": Phrase(
            "முகவரி விவரங்கள் எதுவும் கிடைக்கவில்லை. தயவுசெய்து முகவரியை மீண்டும் சொல்லுங்கள்.",
            "pending",
        ),
        "unverified": Phrase(
            "மொழிபெயர்ப்பை சரிபார்க்க முடியவில்லை. தயவுசெய்து அதை மீண்டும் சொல்லுங்கள், மெதுவாக.",
            "pending",
        ),
    },
}


def repeat_reason(verified: bool, fact_count: int, speaker: Role) -> RepeatReason | None:
    """Why the speaker should repeat, or None when the turn is fine. A failed check wins: the
    listener then got a fallback, whether or not facts were found. Only the customer is expected
    to give address details, so a rider turn without facts ("coming in 2 minutes") is fine."""
    if not verified:
        return "unverified"
    return "no_facts" if speaker == "customer" and not fact_count else None


def repeat_prompt(language: str, reason: RepeatReason) -> Phrase | None:
    """The prompt in `language`, or None when there is no entry (callers omit it, never guess)."""
    return REPEAT_PROMPTS.get(language, {}).get(reason)
