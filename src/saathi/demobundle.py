"""Guided demo: replay stored turns through the real room flow with zero Gnani calls.

A bundle is a directory with bundle.json and one WAV per stored turn. A turn is matched by the
SHA-256 of the uploaded clip plus its source language, so only the prepared clips replay and nothing
the caller sends can reach Gnani on this path. Facts and landmarks are recomputed locally from the
stored source transcript, the same way the live pipeline does, so the chips and the card behave
exactly as they do live. A listener language with no recorded turn is translated locally and
plays no audio. The bundle is built by scripts/build_demo_bundle.py (a paid, manual step).
"""

import asyncio
import hashlib
import json
import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from saathi.facts import extract_facts
from saathi.landmarks import localize_landmarks
from saathi.pipeline import Timings, TurnResult, translate_transcript
from saathi.translate import Translator

log = logging.getLogger(__name__)

BUNDLE_NAME = "bundle.json"
BUNDLE_VERSION = 1


class NoDemoMatchError(Exception):
    """The uploaded clip and language pair are not in the bundle."""


class BundleTurn(BaseModel):
    clip_sha256: str
    src: str
    tgt: str
    transcript: str
    translation: str
    verified: bool
    audio: str  # file name inside the bundle directory


def clip_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DemoBundle:
    def __init__(self, directory: Path, turns: list[BundleTurn]) -> None:
        self._directory = directory
        self._turns = {(t.clip_sha256, t.src, t.tgt): t for t in turns}
        # The stored transcript belongs to the clip, not to a listener language, so any recorded
        # turn of (clip, source language) can supply it.
        self._transcripts = {(t.clip_sha256, t.src): t.transcript for t in turns}

    def __len__(self) -> int:
        return len(self._turns)

    async def replay(self, clip: bytes, src: str, tgt: str, translator: Translator) -> TurnResult:
        """A prepared clip for any listener language, with no Gnani call on any path.

        A language that was recorded replays its stored translation and audio. Any other is
        translated locally from the stored transcript and has no audio.
        """
        key = (clip_digest(clip), src)
        transcript = self._transcripts.get(key)
        if transcript is None:
            raise NoDemoMatchError
        turn = self._turns.get((*key, tgt))
        if turn is None:
            facts, translation, verified = await translate_transcript(
                transcript, src, tgt, translator
            )
            return TurnResult(
                transcript, translation, b"", Timings(0.0, 0.0, 0.0, 0.0), facts, verified
            )
        audio = (self._directory / turn.audio).read_bytes()
        facts = tuple(extract_facts(transcript, src))
        facts = await asyncio.to_thread(localize_landmarks, facts, src, tgt, translator)
        return TurnResult(
            transcript,
            turn.translation,
            audio,
            Timings(0.0, 0.0, 0.0, 0.0),
            facts=facts,
            verified=turn.verified,
        )


def load_bundle(directory: Path) -> DemoBundle | None:
    """The bundle in `directory`, or None when it is missing or invalid (logged, never fatal)."""
    manifest = directory / BUNDLE_NAME
    if not manifest.is_file():
        return None
    try:
        raw = json.loads(manifest.read_text("utf-8"))
        if raw["version"] != BUNDLE_VERSION:
            raise ValueError("unsupported bundle version")
        turns = [BundleTurn(**item) for item in raw["turns"]]
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        log.warning("demo bundle %s is not valid; guided demo is off", manifest)
        return None
    present = [t for t in turns if (directory / t.audio).is_file()]
    if len(present) != len(turns):
        log.warning("demo bundle %s lists missing audio files; those turns are skipped", manifest)
    return DemoBundle(directory, present) if present else None
