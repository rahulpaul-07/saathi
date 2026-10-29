"""Check the wrong-translation demo clip (kn-wrong-translation) on the kn -> hi path, locally.

Local IndicTrans2 only; no Gnani calls and no audio. The Gnani STT is replaced by the transcript
text, so this shows what the rider would get for the clip: the plain (unmasked) translation next to
the chips, the masked translation, and whether the fact-summary fallback fires. Two transcripts are
run: the clip's source text, and what Gnani STT wrote for the clip on 2026-10-29 (synthetic).

  --replay PATH   also write the replay JSON that scripts/screenshot_server.py needs, built from the
                  STT transcript run, with every translation recorded from the real local model
                  (PATH is under scratch/, which is gitignored)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import cast

from saathi.evaluation.democlips import CLIP_SPECS
from saathi.facts import extract_facts
from saathi.gnani import GnaniClient
from saathi.masking import mask
from saathi.pipeline import TurnResult, run_turn
from saathi.translate import RoutingTranslator

CLIP_ID = "kn-wrong-translation"
SRC, TGT = "kn", "hi"
# Gnani STT output for the clip, from scripts/transcribe_demo.py (no commas, as the STT writes it).
STT_TRANSCRIPT = "ನಮ್ಮ ಮನೆ ಎರಡನೇ ಕ್ರಾಸ್ ಮೂರನೇ ಮೇನ್ ಗೇಟ್ ನಂಬರ್ ಎರಡು ಹತ್ತಿರ ಆಪೋಸಿಟ್ ಗಣೇಶ ದೇವಸ್ಥಾನ"


class RecordingTranslator:
    """The real local model, remembering every input it was given and what it returned."""

    def __init__(self) -> None:
        self._inner = RoutingTranslator()
        self.seen: dict[str, str] = {}

    def translate(self, text: str, src: str, tgt: str) -> str:
        output = self._inner.translate(text, src, tgt)
        self.seen[text] = output
        return output


class TextGnani:
    """Stands in for Gnani: the 'speech' is the transcript text, the audio is empty."""

    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        return self.transcript

    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
        return b""


def run(transcript: str, translator: RecordingTranslator) -> TurnResult:
    gnani = cast(GnaniClient, TextGnani(transcript))
    return asyncio.run(run_turn(b"", SRC, TGT, gnani, translator))


def show(label: str, transcript: str) -> tuple[TurnResult, str, str]:
    translator = RecordingTranslator()
    facts = extract_facts(transcript, SRC)
    plain = translator.translate(transcript, SRC, TGT)
    masked_input = mask(transcript, SRC, facts).text
    result = run(transcript, translator)
    masked_raw = translator.seen[masked_input]
    print(f"== {label}")
    print(f"transcript:   {transcript}")
    print(f"chips:        {', '.join(f'{f.kind} {f.value}' for f in result.facts)}")
    print(f"unmasked hi:  {plain}")
    print(f"masked input: {masked_input}")
    print(f"masked raw:   {masked_raw}")
    print(f"spoken hi:    {result.translation}")
    print(f"verified:     {result.verified}  -> fallback summary fires: {not result.verified}\n")
    return result, plain, masked_raw


def write_replay(path: Path, transcript: str) -> None:
    translator = RecordingTranslator()
    facts = extract_facts(transcript, SRC)
    plain = translator.translate(transcript, SRC, TGT)
    masked_input = mask(transcript, SRC, facts).text
    run(transcript, translator)
    landmark = next(f for f in facts if f.kind == "landmark")
    data = {
        "text": transcript,
        "plain": plain,
        "masked_input": masked_input,
        "masked_raw": translator.seen[masked_input],
        "facts": [
            {"kind": f.kind, "value": f.value, "local": translator.seen.get(f.value)}
            for f in facts
            if f.kind == "landmark"
        ],
    }
    assert landmark.value in translator.seen, "the landmark was not translated on its own"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    spec = next(s for s in CLIP_SPECS if s.id == CLIP_ID)
    show("clip source text", spec.text)
    show("Gnani STT transcript of the clip", STT_TRANSCRIPT)
    if args.replay:
        write_replay(args.replay, STT_TRANSCRIPT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
