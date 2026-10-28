"""Quick replies: fixed phrases either person can send with one tap, in all 10 languages.

Each role has its own three phrases (`IDS_BY_ROLE`). A phrase is sent in the RECIPIENT's language
and is never translated at runtime. English is the source. A phrase's `review_status` is per phrase,
not per language: "reviewed" means the author checked that exact text, "pending" is unreviewed
machine output from `scripts/gen_quick_replies.py`, and the UI warns on pending ones. Phrases
contain no personal data, so their audio may be cached.

The customer's "come_to_gate" cannot carry a gate number in a fixed phrase; the customer says the
number by voice instead (see docs/DECISIONS.md).
"""

from dataclasses import dataclass
from typing import Literal

from saathi.rooms import Role

ReviewStatus = Literal["source", "reviewed", "pending"]
QuickReplyId = Literal[
    "reached_gate",
    "which_floor",
    "coming_2_min",
    "come_to_gate",
    "coming_down",
    "leave_at_security",
]

IDS_BY_ROLE: dict[Role, tuple[QuickReplyId, ...]] = {
    "rider": ("reached_gate", "which_floor", "coming_2_min"),
    "customer": ("come_to_gate", "coming_down", "leave_at_security"),
}


@dataclass(frozen=True)
class Phrase:
    text: str
    review_status: ReviewStatus


QUICK_REPLIES: dict[str, dict[QuickReplyId, Phrase]] = {
    "en": {
        "reached_gate": Phrase("I am at the gate", "source"),
        "which_floor": Phrase("Which floor?", "source"),
        "coming_2_min": Phrase("Coming in 2 minutes", "source"),
        "come_to_gate": Phrase("Come to the gate", "source"),
        "coming_down": Phrase("I'm coming down", "source"),
        "leave_at_security": Phrase("Leave it at the security desk", "source"),
    },
    # Rider phrases for hi and bn were corrected by the author ("reviewed"). Everything else is
    # unreviewed machine output; none of it has been hand-edited.
    "hi": {
        "reached_gate": Phrase("मैं गेट पर हूँ", "reviewed"),
        "which_floor": Phrase("कौन सा फ्लोर?", "reviewed"),
        # Avoids "आ रहा हूँ", which is gendered.
        "coming_2_min": Phrase("बस 2 मिनट", "reviewed"),
        "come_to_gate": Phrase("गेट पर आ जाइए", "reviewed"),
        "coming_down": Phrase("नीचे आ रहे हैं", "reviewed"),
        "leave_at_security": Phrase("सिक्योरिटी पर रख दीजिए", "reviewed"),
    },
    "bn": {
        "reached_gate": Phrase("আমি গেটে আছি", "reviewed"),
        "which_floor": Phrase("কত তলায়?", "reviewed"),
        "coming_2_min": Phrase("২ মিনিটে আসছি", "reviewed"),
        "come_to_gate": Phrase("গেটে চলে আসুন", "reviewed"),
        "coming_down": Phrase("আমি নিচে আসছি", "reviewed"),
        "leave_at_security": Phrase("সিকিউরিটিতে রেখে দিন", "reviewed"),
    },
    "kn": {
        "reached_gate": Phrase("ನಾನು ಬಾಗಿಲಲ್ಲಿದ್ದೇನೆ", "pending"),
        "which_floor": Phrase("ಯಾವ ಮಹಡಿ?", "pending"),
        "coming_2_min": Phrase("2 ನಿಮಿಷಗಳಲ್ಲಿ ಬರುವುದು", "pending"),
        "come_to_gate": Phrase("ಬಾಗಿಲಿಗೆ ಬನ್ನಿ.", "pending"),
        "coming_down": Phrase("ನಾನು ಕೆಳಗಿಳಿಯುತ್ತೇನೆ", "pending"),
        "leave_at_security": Phrase("ಅದನ್ನು ಭದ್ರತಾ ಮೇಜಿನ ಬಳಿ ಬಿಡಿ.", "pending"),
    },
    "te": {
        "reached_gate": Phrase("నేను ద్వారం వద్ద ఉన్నాను", "pending"),
        "which_floor": Phrase("ఏ అంతస్తు?", "pending"),
        "coming_2_min": Phrase("2 నిమిషాల్లో వస్తుంది", "pending"),
        "come_to_gate": Phrase("ద్వారం వద్దకు రండి.", "pending"),
        "coming_down": Phrase("నేను కిందకి వస్తాను", "pending"),
        "leave_at_security": Phrase("దానిని భద్రతా డెస్క్ వద్ద ఉంచండి.", "pending"),
    },
    "gu": {
        "reached_gate": Phrase("હું દ્વાર પર છું.", "pending"),
        "which_floor": Phrase("કયા માળે?", "pending"),
        "coming_2_min": Phrase("2 મિનિટમાં આવે છે", "pending"),
        "come_to_gate": Phrase("દરવાજા પર આવો.", "pending"),
        "coming_down": Phrase("હું નીચે આવી રહ્યો છું", "pending"),
        "leave_at_security": Phrase("તેને સુરક્ષા ડેસ્ક પર મૂકી દો.", "pending"),
    },
    "ml": {
        "reached_gate": Phrase("ഞാൻ വാതിലിലാണ്.", "pending"),
        "which_floor": Phrase("ഏത് നില?", "pending"),
        "coming_2_min": Phrase("2 മിനിറ്റിനുള്ളിൽ വരുന്നു", "pending"),
        "come_to_gate": Phrase("വാതിലിലേക്ക് വരൂ.", "pending"),
        "coming_down": Phrase("ഞാൻ താഴേക്ക് വരുന്നു.", "pending"),
        "leave_at_security": Phrase("അത് സെക്യൂരിറ്റി ഡെസ്കിൽ വെക്കുക.", "pending"),
    },
    "mr": {
        "reached_gate": Phrase("मी दरवाजात आहे.", "pending"),
        "which_floor": Phrase("कोणत्या मजल्यावर?", "pending"),
        "coming_2_min": Phrase("2 मिनिटांत येत आहे", "pending"),
        "come_to_gate": Phrase("दरवाजाकडे या.", "pending"),
        "coming_down": Phrase("मी खाली येतो", "pending"),
        "leave_at_security": Phrase("ते सुरक्षा डेस्कवर ठेवा.", "pending"),
    },
    "pa": {
        "reached_gate": Phrase("ਮੈਂ ਦਰਵਾਜ਼ੇ ਤੇ ਹਾਂ", "pending"),
        "which_floor": Phrase("ਕਿਹਡ਼ੀ ਮੰਜ਼ਲ?", "pending"),
        "coming_2_min": Phrase("2 ਮਿੰਟ ਵਿੱਚ ਆ ਰਿਹਾ ਹੈ", "pending"),
        "come_to_gate": Phrase("ਦਰਵਾਜ਼ੇ ਤੇ ਆਓ।", "pending"),
        "coming_down": Phrase("ਮੈਂ ਹੇਠਾਂ ਆ ਰਿਹਾ ਹਾਂ", "pending"),
        "leave_at_security": Phrase("ਇਸ ਨੂੰ ਸੁਰੱਖਿਆ ਡੈਸਕ'ਤੇ ਛੱਡ ਦਿਓ।", "pending"),
    },
    "ta": {
        "reached_gate": Phrase("நான் வாசலில் இருக்கிறேன்", "pending"),
        "which_floor": Phrase("எந்தத் தளம்?", "pending"),
        "coming_2_min": Phrase("2 நிமிடங்களில் வரும்", "pending"),
        "come_to_gate": Phrase("வாசலுக்கு வாருங்கள்.", "pending"),
        "coming_down": Phrase("நான் கீழே", "pending"),
        "leave_at_security": Phrase("அதை பாதுகாப்பு மேசையில் வைக்கவும்.", "pending"),
    },
}


def phrase_for(language: str, phrase_id: QuickReplyId) -> Phrase | None:
    """The phrase in `language`, or None when there is no entry (callers refuse, never guess)."""
    return QUICK_REPLIES.get(language, {}).get(phrase_id)
