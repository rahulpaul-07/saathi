"""Which placeholder style does IndicTrans2 copy through unchanged? Offline, GPU, no Gnani calls.

  uv run --no-sync python scripts/probe_placeholders.py [--targets bn hi en] [--out FILE]

Masks a few synthetic direction sentences with each candidate template, translates them with the
real models and counts how often every placeholder comes back exactly once. The winner becomes
`PLACEHOLDER_TEMPLATE` in src/saathi/masking.py. Uses the dev split only, so the frozen test split
is not looked at while picking a format.
"""

import argparse
import json
import sys
from pathlib import Path

from saathi.evaluation.factscore import load_gold, select
from saathi.facts import extract_facts
from saathi.languages import LANGUAGES
from saathi.masking import mask, restore
from saathi.translate import RoutingTranslator

GOLD = Path(__file__).resolve().parent.parent / "eval" / "gold" / "directions.json"
# "#L{n}" is matched by the toolkit's own entity wrapping and is restored by it, then by us.
TEMPLATES = ["<ID{n}>", "[ID{n}]", "ID{n}", "#L{n}", "<{n}>", "XQ{n}Z"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--targets", nargs="+", default=["bn", "hi", "kn", "en"])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    for tgt in args.targets:
        if tgt not in LANGUAGES:
            print(f"unknown language {tgt!r}", file=sys.stderr)
            return 2

    translator = RoutingTranslator()
    utterances = select(load_gold(GOLD), "dev")
    results: dict[str, dict[str, int]] = {}
    for template in TEMPLATES:
        ok = total = 0
        for utterance in utterances:
            facts = extract_facts(utterance.text, utterance.lang)
            masked = mask(utterance.text, utterance.lang, facts, template)
            if not masked.slots:
                continue
            for tgt in args.targets:
                if tgt == utterance.lang:
                    continue
                raw = translator.translate(masked.text, utterance.lang, tgt)
                total += 1
                ok += restore(raw, masked, tgt, template).verified
        results[template] = {"verified": ok, "total": total}
        print(f"{template:<8} {ok}/{total} all placeholders returned once")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
