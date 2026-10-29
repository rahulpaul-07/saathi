"""Serve the real app with fakes that replay one real local translation, for README screenshots.

No Gnani and no model: the replayed texts come from a local IndicTrans2 run on the synthetic gold
clip kn-wrong-translation (kn -> hi), saved as JSON by scripts/check_kn_hi.py --replay. MODE picks
what the rider sees:
  unmasked  the toolkit's plain translation next to the chips (what a naive pipeline would speak)
  masked    the real pipeline with masking on (its placeholder check and fallback included)
Run: uv run --no-sync python scripts/screenshot_server.py <replay.json> <unmasked|masked> <port>
"""

import json
import sys
from pathlib import Path
from typing import cast

import uvicorn
from pydantic import SecretStr

from saathi import pipeline
from saathi.app import create_app
from saathi.config import Settings
from saathi.facts import Fact
from saathi.gnani import GnaniClient
from saathi.masking import MaskedTranslation
from saathi.translate import Translator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "e2e"))
from serve import FakeGnani  # noqa: E402  (shares the silent-audio fake with the e2e server)


class Replay:
    """Returns the recorded model output for each input it was recorded with, else fails loudly."""

    def __init__(self, outputs: dict[str, str]) -> None:
        self.outputs = outputs

    def translate(self, text: str, src: str, tgt: str) -> str:
        return self.outputs[text]


class SpokenGnani(FakeGnani):
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        return self.transcript


def main() -> None:
    replay_path, mode, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    data = json.loads(Path(replay_path).read_text(encoding="utf-8"))
    landmark = next(fact for fact in data["facts"] if fact["kind"] == "landmark")
    translator: Translator = Replay(
        {
            data["text"]: data["plain"],
            data["masked_input"]: data["masked_raw"],
            landmark["value"]: landmark["local"],
        }
    )
    if mode == "unmasked":

        def plain(
            translator: Translator, transcript: str, src: str, tgt: str,
            facts: tuple[Fact, ...], use_mask: bool,
        ) -> MaskedTranslation:
            text = translator.translate(transcript, src, tgt)
            return MaskedTranslation(text, verified=True, raw=text)

        pipeline._translate_checked = plain  # screenshot harness only
    app = create_app(
        Settings(gnani_api_key=SecretStr("dummy")),
        gnani=cast(GnaniClient, SpokenGnani(data["text"])),
        translator=translator,
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
