"""Print machine translations (English -> X, local IndicTrans2, no network) of the quick replies.

  uv run --no-sync python scripts/gen_quick_replies.py

Only phrases missing from src/saathi/quickreplies.py are translated; reviewed texts are never
touched. The output is a table to read and a Python block to paste into the data, marked
"pending" until a speaker has checked it. Needs the en-indic model (downloaded once from HF).
"""

import sys

from saathi.languages import LANGUAGES
from saathi.quickreplies import IDS_BY_ROLE, QUICK_REPLIES, QuickReplyId
from saathi.translate import RoutingTranslator

SOURCE = "en"


def main() -> int:
    english = QUICK_REPLIES[SOURCE]
    ids: list[QuickReplyId] = [i for role_ids in IDS_BY_ROLE.values() for i in role_ids]
    translator = RoutingTranslator()
    translator.load(("en-indic",))

    generated: dict[str, dict[QuickReplyId, str]] = {}
    for code in LANGUAGES:
        if code == SOURCE:
            continue
        have = QUICK_REPLIES.get(code, {})
        for phrase_id in ids:
            if phrase_id not in have:
                text = translator.translate(english[phrase_id].text, SOURCE, code)
                generated.setdefault(code, {})[phrase_id] = text

    print(f"{'lang':<5}{'id':<20}{'english':<34}machine translation")
    for code, rows in generated.items():
        for phrase_id, text in rows.items():
            print(f"{code:<5}{phrase_id:<20}{english[phrase_id].text:<34}{text}")

    print("\n# Paste into QUICK_REPLIES (status pending until a speaker reviews each text):")
    for code, rows in generated.items():
        print(f'    "{code}": {{')
        for phrase_id, text in rows.items():
            print(f'        "{phrase_id}": Phrase("{text}", "pending"),')
        print("    },")
    return 0


if __name__ == "__main__":
    sys.exit(main())
