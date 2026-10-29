"""Synthesize the gold direction sentences with Gnani TTS (spends credits).

  --dry-run   list the sentences and the ledger total; sends nothing, needs no key
  (default)   one TTS call per sentence through the ledger, saved as 16 kHz mono 16-bit WAV in
              eval/audio/gold_tts/<gold id>.wav (gitignored); existing files are not regenerated

Clean synthetic speech: the fact-accuracy set for scripts/eval_noise.py --audio-dir. It says
nothing about real speakers; real human speech comes from FLEURS (scripts/eval_speech.py).
Real runs only while the author is awake, after reviewing --dry-run.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from saathi.config import get_settings
from saathi.evaluation.calls import (
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.evaluation.factscore import load_gold
from saathi.evaluation.wavtools import resample_to_16k
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "gold" / "directions.json"
OUT_DIR = ROOT / "eval" / "audio" / "gold_tts"
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"
LEDGER_LABEL = "gold-tts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()

    ledger = CallLedger(args.ledger)
    todo = [u for u in load_gold(args.gold) if not (args.out_dir / f"{u.id}.wav").is_file()]
    for u in todo:
        print(f"  {u.id} {u.lang}  TTS x1")
    print(f"Calls: {len(todo)}; ledger {ledger.total}/{ledger.cap} -> {ledger.total + len(todo)}")
    if ledger.total + len(todo) > ledger.cap:
        print("REFUSED: over the call cap.")
        return 2
    if args.dry_run or not todo:
        print("Dry run: nothing was sent." if args.dry_run else "Nothing to do.")
        return 0
    gnani = MeteredGnani(get_settings(), ledger, LEDGER_LABEL)

    async def go() -> None:
        limiter = SlidingWindowLimiter()
        args.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            for u in todo:
                voice = LANGUAGES[u.lang]
                await limiter.acquire(1)
                wav = await gnani.synthesize(u.text, voice.gnani_code, voice.tts_voice)
                (args.out_dir / f"{u.id}.wav").write_bytes(resample_to_16k(wav))
        finally:
            await gnani.aclose()

    try:
        asyncio.run(go())
    except BudgetExceededError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except GnaniError as exc:
        print(f"stopped by Gnani error {exc.status}; finished files are kept", file=sys.stderr)
        return 1
    print(f"wrote {len(todo)} files to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
