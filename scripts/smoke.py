"""Slice 1 smoke test: confirm the real Gnani endpoints work and measure what a call costs.

Usage:
  uv run python scripts/smoke.py --langs bn          # TTS -> STT round trip (2 API calls)
  uv run python scripts/smoke.py --langs bn --ogg    # also probe OGG/Opus into STT (2 more calls)
  uv run python scripts/smoke.py --audio rec.webm --lang bn   # STT only (1 call), any file

Check the dashboard credit balance before and after to derive credits per call.
"""

import argparse
import asyncio
import time
from collections.abc import Awaitable

from saathi.config import get_settings
from saathi.gnani import GnaniClient, GnaniError
from saathi.languages import LANGUAGES

SAMPLES = {
    "hi": "नमस्ते, आप कैसे हैं?",
    "bn": "নমস্কার, আপনি কেমন আছেন?",
    "kn": "ನಮಸ್ಕಾರ, ನೀವು ಹೇಗಿದ್ದೀರಿ?",
    "ta": "வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?",
}


async def timed[T](label: str, coro: Awaitable[T]) -> T:
    start = time.perf_counter()
    result = await coro
    print(f"  {label}: {(time.perf_counter() - start) * 1000:.0f} ms")
    return result


async def roundtrip(client: GnaniClient, lang: str, ogg: bool) -> None:
    info = LANGUAGES[lang]
    text = SAMPLES[lang]
    print(f"[{lang}] input : {text}")
    formats = [("wav", "wav")] + ([("ogg", "ogg")] if ogg else [])
    for container, ext in formats:
        audio = await timed(
            f"TTS {container}",
            client.synthesize(text, info.gnani_code, info.tts_voice, container=container),
        )
        print(f"  audio bytes: {len(audio)}, magic: {audio[:4]!r}")
        transcript = await timed(
            f"STT from {container}", client.transcribe(audio, f"clip.{ext}", info.gnani_code)
        )
        print(f"[{lang}] output: {transcript}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", nargs="*", default=[], choices=list(LANGUAGES))
    parser.add_argument("--ogg", action="store_true")
    parser.add_argument("--audio")
    parser.add_argument("--lang", choices=list(LANGUAGES))
    args = parser.parse_args()

    client = GnaniClient(get_settings())
    try:
        for lang in args.langs:
            await roundtrip(client, lang, args.ogg)
        if args.audio and args.lang:
            with open(args.audio, "rb") as handle:
                data = handle.read()
            name = args.audio.rsplit("\\", 1)[-1]
            text = await timed(
                f"STT {name}", client.transcribe(data, name, LANGUAGES[args.lang].gnani_code)
            )
            print(f"transcript: {text}")
    except GnaniError as exc:
        print(f"FAILED: {exc} (upstream status {exc.status}); see log output above")
    finally:
        await client.aclose()


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
