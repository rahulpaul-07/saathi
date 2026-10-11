"""Day-one probe: how Gnani STT writes numbers and English words in Kannada and English output.

  uv run --no-sync python scripts/probe_codemix.py            dry run (default): no calls
  uv run --no-sync python scripts/probe_codemix.py --spend    make the calls (counted in the ledger)

Synthetic addresses only. Audio goes to eval/audio/probe/ (gitignored); the transcripts, which are
synthetic, go to eval/results/probe_codemix.json. The audio is Gnani TTS fed to Gnani STT, so this
shows how transcripts are WRITTEN (digits, number words, Latin or Kannada script), not how well
real code-mixed speech is recognised.
"""

import argparse
import asyncio
import json
import sys
from functools import partial
from pathlib import Path

from saathi.config import get_settings
from saathi.evaluation.calls import (
    GNANI_CALL_CAP,
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.evaluation.probe import (
    PLANNED_PROBE_CALLS,
    PROBE_CALL_CAP,
    PROBE_TEXTS,
    STT_CALLS,
    TTS_CALLS,
    ProbeText,
    classify_transcript,
)
from saathi.evaluation.turns import call_with_retry
from saathi.evaluation.wavtools import resample_to_16k
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES

AUDIO_DIR = Path("eval/audio/probe")
RESULT_FILE = Path("eval/results/probe_codemix.json")
LEDGER_PATH = Path("eval/state/gnani_ledger.json")
LABEL = "probe"
# Voices from the Timbre v2.5 catalog (docs.gnani.ai TTS voices): en-IN Kaveri, kn-IN Saanvi.
VOICES = {"kn-IN": LANGUAGES["kn"].tts_voice, "en-IN": "Kaveri"}


def print_plan() -> None:
    ledger = CallLedger(LEDGER_PATH)
    print("DRY RUN: no calls are made. Pass --spend to run.\n")
    for item in PROBE_TEXTS:
        stt = ", ".join(item.stt_languages)
        print(f"  {item.key:22} TTS {item.tts_language} ({VOICES[item.tts_language]}) -> STT {stt}")
        print(f"      {item.text}")
    print(
        f"\nCalls: {TTS_CALLS} TTS + {STT_CALLS} STT = {PLANNED_PROBE_CALLS}; "
        f"probe cap {PROBE_CALL_CAP} (retries after a 429 count); pacing 3 calls per 10 s."
    )
    print(f"Ledger (all steps): {ledger.total} spent of the global cap {GNANI_CALL_CAP}.")


async def run_probe() -> int:
    ledger = CallLedger(LEDGER_PATH)
    gnani = MeteredGnani(get_settings(), ledger, LABEL)
    limiter = SlidingWindowLimiter()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    def check_cap() -> None:
        if ledger.spent(LABEL) >= PROBE_CALL_CAP:
            raise BudgetExceededError(f"probe cap of {PROBE_CALL_CAP} calls reached")

    async def speak(item: ProbeText) -> bytes:
        check_cap()
        wav, _ = await call_with_retry(
            partial(gnani.synthesize, item.text, item.tts_language, VOICES[item.tts_language]),
            limiter,
        )
        return resample_to_16k(wav)

    try:
        for item in PROBE_TEXTS:
            audio = await speak(item)
            (AUDIO_DIR / f"{item.key}.wav").write_bytes(audio)
            for language in item.stt_languages:
                check_cap()
                transcript, retries = await call_with_retry(
                    partial(gnani.transcribe, audio, "turn.wav", language), limiter
                )
                rows.append(
                    {
                        "key": item.key,
                        "text": item.text,
                        "stt_language": language,
                        "transcript": transcript,
                        "tokens_by_form": classify_transcript(transcript),
                        "retries": retries,
                    }
                )
                print(f"{item.key} [{language}]: {transcript}")
    except (GnaniError, BudgetExceededError) as exc:
        print(f"stopped: {exc}; {len(rows)} transcripts kept", file=sys.stderr)
        return 1
    finally:
        await gnani.aclose()
        RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RESULT_FILE.write_text(
            json.dumps(
                {
                    "audio": "clean synthetic (Gnani TTS fed to Gnani STT), synthetic addresses",
                    "rows": rows,
                    "calls_spent": ledger.spent(LABEL),
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    print(f"wrote {RESULT_FILE}; ledger {ledger.total}/{GNANI_CALL_CAP}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="print the plan only (default)")
    group.add_argument("--spend", action="store_true", help="make the Gnani calls")
    args = parser.parse_args()
    if not args.spend:
        print_plan()
        return 0
    return asyncio.run(run_probe())


if __name__ == "__main__":
    sys.exit(main())
