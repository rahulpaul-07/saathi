"""Demo clips: synthetic Gnani TTS utterances mixed with licensed street noise.

Every clip is synthetic speech about a made-up address; none is a recording of a person. The
texts are written here (digits spelled as words, as in eval/gold/directions.json) and are the
only input, so the clips can be regenerated and the call count is known in advance.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from saathi.evaluation import noisemix
from saathi.evaluation.wavtools import resample_to_16k
from saathi.facts import extract_facts
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
    # What the sentence is meant to carry: (kind, value, lowercase English words that would show
    # the fact survived a back-translation). Used by scripts/backtranslate_demo.py only.
    facts: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


# kn text for "wrong-translation" is gold utterance g02; the others are new synthetic addresses.
CLIP_SPECS = (
    ClipSpec(
        "kn-wrong-translation",
        "kn",
        "Gate 2, Ganesha temple",
        "ನಮ್ಮ ಮನೆ ಎರಡನೇ ಕ್ರಾಸ್, ಮೂರನೇ ಮೇನ್, ಗೇಟ್ ನಂಬರ್ ಎರಡು ಹತ್ತಿರ, ಆಪೋಸಿಟ್ ಗಣೇಶ ದೇವಸ್ಥಾನ",
        "fluent but wrong translation, chips correct (kn to hi)",
        (
            ("cross", "2", ("2", "two", "second", "2nd")),
            ("main", "3", ("3", "three", "third", "3rd")),
            ("gate", "2", ("2", "two", "second", "2nd")),
            ("landmark", "Ganesha temple", ("ganesh",)),
        ),
    ),
    ClipSpec(
        "kn-bakery",
        "kn",
        "Gate 4, bakery",
        "ಮೂರನೇ ಕ್ರಾಸ್, ಐದನೇ ಮೇನ್, ಗೇಟ್ ನಂಬರ್ ನಾಲ್ಕು, ಬೇಕರಿ ಪಕ್ಕ",
        "plain turn (kn to hi)",
        (
            ("cross", "3", ("3", "three", "third", "3rd")),
            ("main", "5", ("5", "five", "fifth", "5th")),
            ("gate", "4", ("4", "four", "fourth", "4th")),
            ("landmark", "bakery", ("bakery",)),
        ),
    ),
    ClipSpec(
        "kn-gate-correction",
        "kn",
        "Sorry, gate 2",
        "ಕ್ಷಮಿಸಿ, ಗೇಟ್ ನಂಬರ್ ಎರಡು",
        "spoken correction after kn-bakery: only the gate changes, 4 to 2 (kn to hi)",
        (("gate", "2", ("2", "two", "second", "2nd")),),
    ),
    ClipSpec(
        "ta-gate",
        "ta",
        "Gate 3, bakery",
        "இரண்டாவது கிராஸ், மூன்றாவது மெயின், கேட் நம்பர் மூன்று, பேக்கரி எதிரில்",
        "plain turn (ta to hi)",
        (
            ("cross", "2", ("2", "two", "second", "2nd")),
            ("main", "3", ("3", "three", "third", "3rd")),
            ("gate", "3", ("3", "three", "third", "3rd")),
            ("landmark", "bakery", ("bakery",)),
        ),
    ),
    ClipSpec(
        "te-gate",
        "te",
        "Gate 1, Hanuman temple",
        "రెండో క్రాస్, నాలుగో మెయిన్, గేట్ నంబర్ ఒకటి, హనుమాన్ గుడి ఎదురుగా",
        "plain turn (te to en)",
        (
            ("cross", "2", ("2", "two", "second", "2nd")),
            ("main", "4", ("4", "four", "fourth", "4th")),
            ("gate", "1", ("1", "one", "first", "1st")),
            ("landmark", "Hanuman temple", ("hanuman",)),
        ),
    ),
)


class Synthesizer(Protocol):
    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes: ...


class Limiter(Protocol):
    async def acquire(self, calls: int = 1) -> None: ...


def clips_without_chips(transcripts: dict[str, str]) -> list[str]:
    """Clip ids whose STT transcript yields no chips.

    The extractor sees the recognizer's transcript, not the sentence we wrote, so this is the
    only check that says whether a demo clip will show chips on the rider screen.
    """
    by_id = {spec.id: spec for spec in CLIP_SPECS}
    return [
        clip_id
        for clip_id, text in transcripts.items()
        if not extract_facts(text, by_id[clip_id].lang)
    ]


def planned_calls(specs: tuple[ClipSpec, ...] = CLIP_SPECS) -> int:
    return len(specs)


def select_specs(ids: Sequence[str] | None) -> tuple[ClipSpec, ...]:
    """The specs to generate: all of them, or only the named ones in table order."""
    if ids is None:
        return CLIP_SPECS
    unknown = sorted(set(ids) - {s.id for s in CLIP_SPECS})
    if unknown:
        raise ValueError(f"unknown clip id: {', '.join(unknown)}")
    return tuple(s for s in CLIP_SPECS if s.id in ids)


def _kept_manifest_entries(out_dir: Path, regenerated: set[str]) -> list[dict[str, str]]:
    """Entries of an earlier manifest whose clip was not regenerated and whose wav still exists."""
    try:
        old = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))["clips"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [
        entry
        for entry in old
        if isinstance(entry, dict)
        and entry.get("id") not in regenerated
        and (out_dir / f"{entry.get('id')}.wav").is_file()
    ]


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
    # A partial run (--only) must not drop the clips it did not regenerate.
    entries = _kept_manifest_entries(out_dir, {s.id for s in specs})
    entries += [{"id": s.id, "lang": s.lang, "label": s.label} for s in specs]
    order = {s.id: i for i, s in enumerate(CLIP_SPECS)}
    entries.sort(key=lambda e: order.get(e["id"], len(order)))
    manifest = {"clips": entries}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
