"""Demo clips: synthetic Gnani TTS utterances mixed with licensed street noise.

Every clip is synthetic speech about a made-up address; none is a recording of a person. The
texts are written here (digits spelled as words, as in eval/gold/directions.json) and are the
only input, so the clips can be regenerated and the call count is known in advance.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from saathi.evaluation import noisemix
from saathi.evaluation.wavtools import resample_to_16k
from saathi.languages import LANGUAGES

LEDGER_LABEL = "demo-tts"
DEMO_SNR_DB = 10.0
DEFAULT_SEED = 20261029


@dataclass(frozen=True)
class ClipSpec:
    id: str
    lang: str
    label: str
    text: str
    role: str  # what the clip shows in the demo video, for the shot list


# kn text for "wrong-translation" is gold utterance g02; the others are new synthetic addresses.
CLIP_SPECS = (
    ClipSpec(
        "kn-wrong-translation",
        "kn",
        "Gate 2, Ganesha temple",
        "ನಮ್ಮ ಮನೆ ಎರಡನೇ ಕ್ರಾಸ್, ಮೂರನೇ ಮೇನ್, ಗೇಟ್ ನಂಬರ್ ಎರಡು ಹತ್ತಿರ, ಆಪೋಸಿಟ್ ಗಣೇಶ ದೇವಸ್ಥಾನ",
        "fluent but wrong translation, chips correct (kn to bn)",
    ),
    ClipSpec(
        "kn-bakery",
        "kn",
        "Gate 4, bakery",
        "ಮೂರನೇ ಕ್ರಾಸ್, ಐದನೇ ಮೇನ್, ಗೇಟ್ ನಂಬರ್ ನಾಲ್ಕು, ಬೇಕರಿ ಪಕ್ಕ",
        "plain turn (kn to bn)",
    ),
    ClipSpec(
        "ta-gate",
        "ta",
        "Gate 3, bakery",
        "இரண்டாவது கிராஸ், மூன்றாவது மெயின், கேட் நம்பர் மூன்று, பேக்கரி எதிரில்",
        "plain turn (ta to hi)",
    ),
    ClipSpec(
        "te-gate",
        "te",
        "Gate 1, Hanuman temple",
        "రెండో క్రాస్, నాలుగో మెయిన్, గేట్ నంబర్ ఒకటి, హనుమాన్ గుడి ఎదురుగా",
        "plain turn (te to en)",
    ),
)


class Synthesizer(Protocol):
    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes: ...


class Limiter(Protocol):
    async def acquire(self, calls: int = 1) -> None: ...


def planned_calls(specs: tuple[ClipSpec, ...] = CLIP_SPECS) -> int:
    return len(specs)


def mix_clip(tts_wav: bytes, noise: noisemix.Samples, seed: int, clip_id: str) -> bytes:
    speech = noisemix.read_wav(resample_to_16k(tts_wav))
    return noisemix.mix_at_snr(
        speech, noise, DEMO_SNR_DB, noisemix.derive_seed(seed, clip_id)
    ).wav


async def build_clips(
    specs: tuple[ClipSpec, ...],
    gnani: Synthesizer,
    limiter: Limiter,
    noise: noisemix.Samples,
    out_dir: Path,
    seed: int = DEFAULT_SEED,
) -> None:
    """Synthesize and mix each clip, writing <id>.wav and the manifest the server reads."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        voice = LANGUAGES[spec.lang]
        await limiter.acquire(1)
        tts_wav = await gnani.synthesize(spec.text, voice.gnani_code, voice.tts_voice)
        (out_dir / f"{spec.id}.wav").write_bytes(mix_clip(tts_wav, noise, seed, spec.id))
    manifest = {"clips": [{"id": s.id, "lang": s.lang, "label": s.label} for s in specs]}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
