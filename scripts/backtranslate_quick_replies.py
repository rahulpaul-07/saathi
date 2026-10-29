"""Back-translate quick replies to English, as a read-through for non-speakers.

Local IndicTrans2 indic-en, greedy; no Gnani calls and no audio. Prints a table of role, id, review
status, the stored text, the English source and the back-translation, and flags a phrase when none
of the keywords for its meaning appears in the back-translation. It flags, it does not prove: a
machine back-translation cannot tell whether a phrase is natural to a native speaker, and a
flagged phrase may only be worded differently.

  uv run --no-sync python scripts/backtranslate_quick_replies.py [LANG ...]   (default: all but en)
"""

import sys

from saathi.languages import LANGUAGES
from saathi.quickreplies import IDS_BY_ROLE, phrase_for
from saathi.translate import RoutingTranslator

# Lowercase words, any one of which shows the meaning of the English source survived.
MEANING: dict[str, tuple[str, ...]] = {
    "reached_gate": ("gate",),
    "which_floor": ("floor",),
    "coming_2_min": ("2 minutes", "two minutes", "2 min", "two min"),
    "come_to_gate": ("gate",),
    "coming_down": ("down",),
    "leave_at_security": ("security",),
}


def drifted(phrase_id: str, back: str) -> bool:
    keywords = MEANING.get(phrase_id)
    return keywords is not None and not any(word in back.lower() for word in keywords)


def main() -> int:
    languages = sys.argv[1:] or [code for code in LANGUAGES if code != "en"]
    unsupported = [code for code in languages if code not in LANGUAGES or code == "en"]
    if unsupported:
        print(f"unsupported language for back-translation: {unsupported!r}", file=sys.stderr)
        return 2
    translator = RoutingTranslator()
    flagged = 0
    for language in languages:
        print(f"== {language}")
        for role, ids in IDS_BY_ROLE.items():
            for phrase_id in ids:
                phrase = phrase_for(language, phrase_id)
                source = phrase_for("en", phrase_id)
                if phrase is None or source is None:
                    print(f"{role:9} {phrase_id:13} missing")
                    continue
                back = translator.translate(phrase.text, language, "en")
                flag = "DRIFT" if drifted(phrase_id, back) else "ok"
                flagged += flag == "DRIFT"
                print(f"{role:9} {phrase_id:13} {phrase.review_status:9} {flag:5} {phrase.text}")
                print(f"{'':38} source: {source.text!r}  back: {back!r}")
    print(f"\n{flagged} phrase(s) flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
