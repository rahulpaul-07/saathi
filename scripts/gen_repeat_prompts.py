"""Print machine translations (English -> X, local IndicTrans2, no network) of the please-repeat
prompts.

  uv run --no-sync python scripts/gen_repeat_prompts.py

Only prompts missing from src/saathi/repeatprompts.py are translated. The output is a Python block
to paste into the data, marked "pending" until a speaker has checked it. Needs the en-indic model.
"""

import sys

from saathi.languages import LANGUAGES
from saathi.repeatprompts import REPEAT_PROMPTS, RepeatReason
from saathi.translate import RoutingTranslator

SOURCE = "en"


def main() -> int:
    english = REPEAT_PROMPTS[SOURCE]
    reasons: list[RepeatReason] = list(english)
    translator = RoutingTranslator()
    translator.load(("en-indic",))

    print("# Paste into REPEAT_PROMPTS (status pending until a speaker reviews each text):")
    for code in LANGUAGES:
        if code == SOURCE:
            continue
        have = REPEAT_PROMPTS.get(code, {})
        missing = [reason for reason in reasons if reason not in have]
        if not missing:
            continue
        print(f'    "{code}": {{')
        for reason in missing:
            text = translator.translate(english[reason].text, SOURCE, code)
            print(f'        "{reason}": Phrase("{text}", "pending"),')
        print("    },")
    return 0


if __name__ == "__main__":
    sys.exit(main())
