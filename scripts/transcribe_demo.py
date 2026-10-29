"""Send the demo clips through Gnani STT and show what chips the transcripts give (spends credits).

  --dry-run   list the clips and the ledger total; sends nothing, needs no key
  (default)   one STT call per clip through the ledger; prints each raw transcript, the chips
              extracted from it and the intended facts; exit 1 if any clip yields no chips

Transcripts are printed, never saved: the demo addresses are invented, but the repo's rule is that
no transcript is stored. Reads demo/clips/ from scripts/make_demo_clips.py (street noise at 10 dB
included, as in the demo). At most 4 calls per run.
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
from saathi.evaluation.democlips import CLIP_SPECS, clips_without_chips
from saathi.facts import extract_facts
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES

ROOT = Path(__file__).resolve().parent.parent
CLIP_DIR = ROOT / "demo" / "clips"
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"
LEDGER_LABEL = "demo-stt"
MAX_CALLS = 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clip-dir", type=Path, default=CLIP_DIR)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()

    ledger = CallLedger(args.ledger)
    missing = [s.id for s in CLIP_SPECS if not (args.clip_dir / f"{s.id}.wav").is_file()]
    for spec in CLIP_SPECS:
        print(f"  {spec.id:22} {spec.lang}  STT x1")
    calls = len(CLIP_SPECS)
    print(f"Calls: {calls} (max {MAX_CALLS}); ledger {ledger.total}/{ledger.cap} -> "
          f"{ledger.total + calls}")
    if missing:
        print(f"Missing clips: {', '.join(missing)}; run scripts/make_demo_clips.py")
        return 1
    if calls > MAX_CALLS or ledger.total + calls > ledger.cap:
        print("REFUSED: over the call limit or the cap.")
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0

    gnani = MeteredGnani(get_settings(), ledger, LEDGER_LABEL)
    transcripts: dict[str, str] = {}

    async def go() -> None:
        limiter = SlidingWindowLimiter()
        try:
            for spec in CLIP_SPECS:
                await limiter.acquire(1)
                audio = (args.clip_dir / f"{spec.id}.wav").read_bytes()
                code = LANGUAGES[spec.lang].gnani_code
                text = await gnani.transcribe(audio, f"{spec.id}.wav", code)
                transcripts[spec.id] = text.strip()
        finally:
            await gnani.aclose()

    try:
        asyncio.run(go())
    except BudgetExceededError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except GnaniError as exc:
        print(f"stopped by Gnani error {exc.status}", file=sys.stderr)
        return 1

    for spec in CLIP_SPECS:
        text = transcripts[spec.id]
        chips = ", ".join(f"{f.kind} {f.value}" for f in extract_facts(text, spec.lang))
        intended = ", ".join(f"{kind} {value}" for kind, value, _ in spec.facts)
        print(f"\n{spec.id} ({spec.lang})\n  transcript: {text}")
        print(f"  chips:      {chips or 'none'}\n  intended:   {intended}")
    empty = clips_without_chips(transcripts)
    print(f"\nclips with no chips: {', '.join(empty) if empty else 'none'}")
    return 1 if empty else 0


if __name__ == "__main__":
    sys.exit(main())
