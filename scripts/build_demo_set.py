"""Build the 50-clip guided demo (demo/clip_set.json) into demo/clips/ and demo/bundle/.

  --dry-run   list every paid step, the call count and the ledger total; sends nothing, no key
  --run       perform the missing steps: customer speech (TTS), transcription (STT), rider speech
              (TTS) for each new clip, through the call ledger
  --manifest  rewrite demo/clips/manifest.json from the stored transcripts; no calls, no key
  --retry-failed  also retry clips that failed on an earlier run (a failed step is never retried
                  within a run, and never silently on the next one)

At least 3 s between calls, one HTTP attempt per call, and progress saved after every step, so a
stopped run resumes without paying for the same step twice. Needs eval/audio/noise/street.wav.
Real runs spend credits: read the --dry-run output first.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from saathi.config import get_settings
from saathi.evaluation import noisemix
from saathi.evaluation.calls import (
    GNANI_CALL_CAP,
    BudgetExceededError,
    CallLedger,
    SingleAttemptGnani,
)
from saathi.evaluation.democlips import DEFAULT_SEED
from saathi.evaluation.demoset import (
    CALLS_PER_NEW_CLIP,
    Layout,
    build_set,
    compare_facts,
    load_clip_set,
    load_progress,
    pending_steps,
    planned_calls,
    read_turns,
    set_problems,
    write_manifest,
)
from saathi.facts import extract_facts
from saathi.translate import RoutingTranslator

ROOT = Path(__file__).resolve().parent.parent
CLIP_SET = ROOT / "demo" / "clip_set.json"
STREET = ROOT / "eval" / "audio" / "noise" / "street.wav"
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"
LEDGER_LABEL = "demo-set"
DEFAULT_RUN_CAP = 150  # the agreed hard cap for one run unless --run-cap lowers it


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--manifest", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--run-cap", type=int, default=DEFAULT_RUN_CAP, help="hard cap on calls this run"
    )
    parser.add_argument("--clip-set", type=Path, default=CLIP_SET)
    parser.add_argument("--clips-dir", type=Path, default=ROOT / "demo" / "clips")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "demo" / "bundle")
    parser.add_argument("--street-file", type=Path, default=STREET)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()

    clips = load_clip_set(args.clip_set)
    problems = set_problems(clips)
    if problems:
        print("clip set is incomplete: " + "; ".join(problems), file=sys.stderr)
        return 1
    layout = Layout(args.clips_dir, args.out_dir)
    progress = load_progress(layout.bundle_dir)
    turns = read_turns(layout.bundle_dir)
    if args.manifest:
        written = write_manifest(clips, layout)
        per_language = {
            lang: sum(1 for c in clips if c.lang == lang and c.id in written)
            for lang in sorted({c.lang for c in clips})
        }
        print(f"manifest lists {len(written)} of {len(clips)} clips: {per_language}")
        print("Rewrote the manifest from stored transcripts; no calls were made.")
        return 0
    ledger = CallLedger(args.ledger)
    calls = planned_calls(clips, layout, progress, args.retry_failed)

    for clip in clips:
        steps = pending_steps(clip, layout, progress, turns)
        skip = clip.id in progress.failures and not args.retry_failed
        note = "existing, kept" if clip.existing else ("failed earlier, skipped" if skip else "")
        names = " ".join({"tts": "TTS", "stt": "STT", "rider": "TTS(rider)"}[s] for s in steps)
        print(f"  {clip.id:22} {clip.type:10} {clip.lang} -> {clip.tgt}  {names or '-':20} {note}")
    heard_ok = sum(1 for c in clips if not compare_facts(c.expected, extract_facts(c.text, c.lang)))
    print(f"Source-text pre-check (no calls): {heard_ok}/{len(clips)} texts read back as expected")
    print(
        f"Calls: {calls} ({CALLS_PER_NEW_CLIP} per new clip); "
        f"ledger {ledger.total}/{ledger.cap} -> {ledger.total + calls}; run cap {args.run_cap}"
    )
    if calls > args.run_cap or ledger.total + calls > ledger.cap:
        print("REFUSED: over the call cap.")
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0

    try:
        noise = noisemix.read_wav(args.street_file.read_bytes())
    except (OSError, noisemix.NoiseMixError) as exc:
        print(f"error: noise file unusable ({type(exc).__name__}); run scripts/fetch_noise.py")
        return 1
    # The run's own ceiling sits above the calls planned only by the agreed margin, never above 150.
    run_ledger = CallLedger(args.ledger, cap=min(GNANI_CALL_CAP, ledger.total + args.run_cap))
    gnani = SingleAttemptGnani(get_settings(), run_ledger, LEDGER_LABEL)
    translator = RoutingTranslator()
    translator.load()

    async def go() -> int:
        try:
            report = await build_set(
                clips,
                gnani,
                translator,
                noise,
                layout,
                DEFAULT_SEED,
                retry_failed=args.retry_failed,
            )
        finally:
            await gnani.aclose()
        print(
            f"built {len(report.built)}, failed {len(report.failed)}, skipped {len(report.skipped)}"
        )
        return 0

    try:
        status = asyncio.run(go())
    except BudgetExceededError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        status = 2
    finally:
        written = write_manifest(clips, layout)
        print(f"manifest lists {len(written)} replayable clips")
        spent = CallLedger(args.ledger)
        made = spent.total - ledger.total
        print(f"Real Gnani calls this run: {made}; ledger {spent.total}/{spent.cap}")
    return status


if __name__ == "__main__":
    sys.exit(main())
