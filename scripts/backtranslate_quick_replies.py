"""Back-translate one language's quick replies to English, as a read-through for non-speakers.

Local IndicTrans2 indic-en, greedy; no Gnani calls and no audio. Prints, for each phrase, its role,
review status, the stored text, the English source and the back-translation. It flags, it does not
prove: a machine back-translation cannot tell whether a phrase is natural to a native speaker.

  uv run --no-sync python scripts/backtranslate_quick_replies.py [LANG]   (default kn)
"""

import sys

from saathi.languages import LANGUAGES
from saathi.quickreplies import IDS_BY_ROLE, phrase_for
from saathi.translate import RoutingTranslator


def main() -> int:
    language = sys.argv[1] if len(sys.argv) > 1 else "kn"
    if language not in LANGUAGES or language == "en":
        print(f"unsupported language for back-translation: {language!r}", file=sys.stderr)
        return 2
    translator = RoutingTranslator()
    print(f"role      id                 status    {language} text -> English back-translation")
    for role, ids in IDS_BY_ROLE.items():
        for phrase_id in ids:
            phrase = phrase_for(language, phrase_id)
            source = phrase_for("en", phrase_id)
            if phrase is None or source is None:
                print(f"{role:9} {phrase_id:18} missing")
                continue
            english = translator.translate(phrase.text, language, "en")
            print(f"{role:9} {phrase_id:18} {phrase.review_status:9} {phrase.text}")
            print(f"{'':28} source: {source.text!r:34} back: {english!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
