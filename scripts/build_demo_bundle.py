"""Build the guided-demo bundle (demo/bundle/) from the prepared demo clips.

  --dry-run   print the exact Gnani call budget and the ledger total; sends nothing, needs no key
  --run       one speech-to-text and one text-to-speech call per clip, through the call ledger

Each clip in demo/clips/manifest.json is run through the real pipeline once for its target
language (TARGETS below); the transcript, the translation and the spoken audio are stored. At
serve time the bundle replays those stored results with no Gnani call (docs/DEPLOY.md). A real run
spends credits, so run it only after reading the --dry-run output.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from saathi.config import get_settings
from saathi.demo import load_demo_clips
from saathi.demobundle import BUNDLE_NAME, BUNDLE_VERSION, clip_digest
from saathi.evaluation.calls import BudgetExceededError, CallLedger, MeteredGnani
from saathi.gnani import GnaniError
from saathi.pipeline import run_turn
from saathi.translate import RoutingTranslator

ROOT = Path(__file__).resolve().parent.parent
CLIPS_DIR = ROOT / "demo" / "clips"
OUT_DIR = ROOT / "demo" / "bundle"
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"
LEDGER_LABEL = "demo-bundle"
CALLS_PER_CLIP = 2  # one STT, one TTS (no retries assumed; a retry would count too)
# The listener's language for each clip's language, matching the pairs in the shot list.
TARGETS = {"kn": "hi", "ta": "hi", "te": "en"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--clips-dir", type=Path, default=CLIPS_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()

    clips = [c for c in load_demo_clips(args.clips_dir).values() if c.lang in TARGETS]
    if not clips:
        print(f"no usable clips in {args.clips_dir}; run scripts/make_demo_clips.py first")
        return 1
    ledger = CallLedger(args.ledger)
    calls = CALLS_PER_CLIP * len(clips)
    for clip in clips:
        print(f"  {clip.id:22} {clip.lang} -> {TARGETS[clip.lang]}  STT x1  TTS x1")
    print(f"Calls: {calls}; ledger {ledger.total}/{ledger.cap} -> {ledger.total + calls}")
    if ledger.total + calls > ledger.cap:
        print("REFUSED: over the call cap.")
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0

    gnani = MeteredGnani(get_settings(), ledger, LEDGER_LABEL)
    translator = RoutingTranslator()
    translator.load()
    turns: list[dict[str, object]] = []

    async def go() -> None:
        try:
            for clip in clips:
                tgt = TARGETS[clip.lang]
                data = (args.clips_dir / f"{clip.id}.wav").read_bytes()
                result = await run_turn(data, clip.lang, tgt, gnani, translator)
                audio_name = f"{clip.id}-{tgt}.wav"
                (args.out_dir / audio_name).write_bytes(result.audio)
                turns.append(
                    {
                        "clip_sha256": clip_digest(data),
                        "src": clip.lang,
                        "tgt": tgt,
                        "transcript": result.transcript,
                        "translation": result.translation,
                        "verified": result.verified,
                        "audio": audio_name,
                    }
                )
        finally:
            await gnani.aclose()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(go())
    except BudgetExceededError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except GnaniError as exc:
        print(f"stopped by Gnani error {exc.status}", file=sys.stderr)
        return 1
    finally:
        # Write what completed, so a stopped run is not paid for twice.
        manifest = {"version": BUNDLE_VERSION, "turns": turns}
        (args.out_dir / BUNDLE_NAME).write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")
    print(f"wrote {len(turns)} turns to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
