"""Build evidence for the ta and te lexicons: probe sentences through local back-translation and,
only when asked, through Gnani TTS then STT (spends credits).

  --table     back-translate each probe sentence with local indic-en; no Gnani calls, no key
  --dry-run   list the planned calls and the ledger total; sends nothing
  (default)   TTS then STT for every sentence, through the ledger; at most 32 calls

The STT transcripts are written to eval/state/lexicon_probe.json (gitignored). They are synthetic
number lists, not addresses.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from saathi.config import get_settings
from saathi.evaluation.calls import (
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.evaluation.lexprobe import (
    LEDGER_LABEL,
    MAX_CALLS,
    RECHECK_MAX_CALLS,
    ProbeBudgetError,
    ProbeSentence,
    all_sentences,
    run_probe,
    ta_ordinal_5_recheck,
)
from saathi.facts.lexicons import EN
from saathi.gnani import GnaniError
from saathi.translate import RoutingTranslator

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"
OUT = ROOT / "eval" / "state" / "lexicon_probe.json"
OUT_RECHECK = ROOT / "eval" / "state" / "lexicon_probe_ordinal5.json"


def numbers_in(english: str) -> set[int]:
    """Every number the English text states, as a digit, "5th" or a word such as "fifth"."""
    found: set[int] = set()
    for token in re.findall(r"[a-z0-9]+", english.lower()):
        digits = re.match(r"\d+", token)
        if digits:
            found.add(int(digits.group()))
        elif token in EN.numbers:
            found.add(EN.numbers[token])
        elif token in EN.ordinals:
            found.add(EN.ordinals[token])
    return found


def missing_values(sentence: ProbeSentence, english: str) -> list[int]:
    stated = numbers_in(english)
    return [item.value for item in sentence.items if item.value not in stated]


def show_table() -> int:
    translator = RoutingTranslator()
    flagged = 0
    for sentence in all_sentences():
        english = translator.translate(sentence.text, sentence.lang, "en")
        lost = missing_values(sentence, english)
        flagged += bool(lost)
        wanted = ", ".join(str(i.value) for i in sentence.items)
        print(f"{sentence.id} ({sentence.lang})  cue: {sentence.cue or '-'}")
        print(f"  source:   {sentence.text}")
        print(f"  English:  {english}")
        first = sentence.items[0]
        form = "ordinal" if first.ordinal else "cardinal"
        print(f"  intended: {first.kind} {form} {wanted}")
        print(f"  verdict:  {'FLAG, missing ' + str(lost) if lost else 'ok'}\n")
    print(f"{flagged} of {len(all_sentences())} sentences flagged")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--ordinal5", action="store_true", help="only the Tamil fifth-ordinal recheck (2 calls)"
    )
    args = parser.parse_args()
    if args.table:
        return show_table()

    ledger = CallLedger(LEDGER)
    sentences = (ta_ordinal_5_recheck(),) if args.ordinal5 else all_sentences()
    out = OUT_RECHECK if args.ordinal5 else OUT
    max_calls = RECHECK_MAX_CALLS if args.ordinal5 else MAX_CALLS
    calls = 2 * len(sentences)
    for sentence in sentences:
        print(f"  {sentence.id:14} TTS x1, STT x1  {sentence.text}")
    print(f"Calls: {calls} (max {max_calls}); ledger {ledger.total}/{ledger.cap} -> "
          f"{ledger.total + calls}")
    if calls > max_calls or ledger.total + calls > ledger.cap:
        print("REFUSED: over the call limit or the cap.")
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0

    gnani = MeteredGnani(get_settings(), ledger, LEDGER_LABEL)

    async def go() -> dict[str, str]:
        try:
            return await run_probe(
                sentences, gnani, SlidingWindowLimiter(), out, max_calls=max_calls
            )
        finally:
            await gnani.aclose()

    try:
        transcripts = asyncio.run(go())
    except (BudgetExceededError, ProbeBudgetError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except GnaniError as exc:
        print(f"stopped by Gnani error {exc.status} (after the one retry); saved progress is kept "
              f"in {out}; ledger now {ledger.total}/{ledger.cap}", file=sys.stderr)
        return 1
    for sentence in sentences:
        print(f"\n{sentence.id}\n  sent:  {sentence.text}\n  heard: {transcripts[sentence.id]}")
    print(f"\nwrote {out}; ledger now {ledger.total}/{ledger.cap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
