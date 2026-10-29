"""Generate the demo clips with Gnani TTS and street noise at 10 dB (spends credits).

  --dry-run   list the clips and the ledger total; sends nothing, needs no key
  (default)   one TTS call per clip through the ledger, then mix and write demo/clips/
  --only ID.. generate just those clips (1 call each); other clips and the manifest are kept

Synthetic speech only. Needs eval/audio/noise/street.wav from scripts/fetch_noise.py. Real runs
only while the author is awake, after reviewing --dry-run.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from saathi.config import get_settings
from saathi.evaluation import noisemix
from saathi.evaluation.calls import (
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.evaluation.democlips import (
    CLIP_SPECS,
    DEFAULT_SEED,
    DEMO_SNR_DB,
    LEDGER_LABEL,
    build_clips,
    planned_calls,
    select_specs,
)
from saathi.gnani import GnaniError

ROOT = Path(__file__).resolve().parent.parent
STREET = ROOT / "eval" / "audio" / "noise" / "street.wav"
OUT_DIR = ROOT / "demo" / "clips"
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="CLIP_ID",
        choices=[s.id for s in CLIP_SPECS],
        help="generate only these clips; the others in --out-dir are kept",
    )
    parser.add_argument("--street-file", type=Path, default=STREET)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    ledger = CallLedger(args.ledger)
    specs = select_specs(args.only)
    calls = planned_calls(specs)
    for spec in specs:
        print(f"  {spec.id:22} {spec.lang}  TTS x1  {spec.role}")
    print(f"Noise: {args.street_file.as_posix()} at {DEMO_SNR_DB:g} dB")
    print(f"Calls: {calls}; ledger {ledger.total}/{ledger.cap} -> {ledger.total + calls}")
    if ledger.total + calls > ledger.cap:
        print("REFUSED: over the call cap.")
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0
    if not args.street_file.is_file():
        print(f"missing {args.street_file}; run scripts/fetch_noise.py", file=sys.stderr)
        return 1
    try:
        noise = noisemix.read_wav(args.street_file.read_bytes())
    except noisemix.NoiseMixError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    gnani = MeteredGnani(get_settings(), ledger, LEDGER_LABEL)

    async def go() -> None:
        try:
            await build_clips(specs, gnani, SlidingWindowLimiter(), noise, args.out_dir, args.seed)
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
    print(f"wrote {len(specs)} clips to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
