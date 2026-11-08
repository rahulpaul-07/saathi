"""Guided demo: replay stored turns through the real room flow with zero Gnani calls.

A bundle is a directory with bundle.json and one WAV per stored turn. A turn is matched by the
SHA-256 of the uploaded clip plus its source language, so only the prepared clips replay and nothing
the caller sends can reach Gnani on this path. A stored turn holds everything the rider sees: the
translation, the facts (landmark rendering included), the verified flag and the spoken audio, and
is served as a plain lookup. A listener language with no stored turn is translated locally and
plays no audio. Bundles are built by scripts/build_demo_set.py and scripts/build_rider_voices.py
(paid, manual steps).
"""

import asyncio
import hashlib
import json
import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from saathi.facts import Fact, extract_facts
from saathi.facts.types import Confidence, FactKind
from saathi.landmarks import localize_landmarks
from saathi.pipeline import Timings, TurnResult, translate_transcript
from saathi.translate import Translator

log = logging.getLogger(__name__)

BUNDLE_NAME = "bundle.json"
BUNDLE_VERSION = 1


class NoDemoMatchError(Exception):
    """The uploaded clip and language pair are not in the bundle."""


class StoredFact(BaseModel):
    """A `Fact` as the rider saw it when the turn was built, landmark rendering included."""

    kind: FactKind
    value: str
    start: int
    end: int
    heard: str
    confidence: Confidence = "high"
    ambiguous: bool = False
    reading: str | None = None
    value_start: int | None = None
    value_end: int | None = None
    local: str | None = None

    @classmethod
    def of(cls, fact: Fact) -> "StoredFact":
        return cls(**vars(fact))

    def to_fact(self) -> Fact:
        return Fact(**self.model_dump())


class BundleTurn(BaseModel):
    clip_sha256: str
    src: str
    tgt: str
    transcript: str
    translation: str
    verified: bool
    audio: str  # file name inside the bundle directory
    # None only for a turn stored before facts were kept; it is then rebuilt locally at serve time.
    facts: list[StoredFact] | None = None


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
        if turn.facts is not None:
            # A complete stored turn: nothing is translated or localised here.
            facts = tuple(stored.to_fact() for stored in turn.facts)
        else:
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
