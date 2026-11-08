"""Stored rider voices: one complete turn for every picker clip in every other rider language.

A turn holds the translation, the facts as the rider sees them (landmark rendering included), the
verified flag and Gnani text-to-speech audio of exactly that text, so the guided demo can serve it
as a lookup. The text is translated locally once per (clip, rider language) and kept in the progress
file until its audio is stored, so a stopped run never speaks a different sentence than the one it
translated. Each missing audio is one paid call, made once: a failure is recorded and not retried.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ValidationError

from saathi.demobundle import BundleTurn, StoredFact, clip_digest
from saathi.evaluation.calls import BudgetExceededError
from saathi.evaluation.demoset import MANIFEST_NAME, read_turns, write_json, write_turns
from saathi.facts import extract_facts
from saathi.gnani import GnaniError
from saathi.landmarks import localize_landmarks
from saathi.languages import LANGUAGES
from saathi.pipeline import TranslationUnavailableError, translate_transcript
from saathi.translate import Translator

PROGRESS_NAME = "voices_progress.json"
MIN_GAP_S = 3.5  # between paid calls, wider than the 3 s of the other evaluation commands


class EmptyTranslationError(Exception):
    """The translation to speak came back empty; there is nothing to send to text-to-speech."""


@dataclass(frozen=True)
class Pair:
    clip_id: str
    sha: str
    src: str
    tgt: str
    transcript: str

    @property
    def key(self) -> str:
        return f"{self.clip_id}|{self.tgt}"

    @property
    def audio_name(self) -> str:
        return f"{self.clip_id}-{self.tgt}.wav"


class PendingText(BaseModel):
    """A translation already made and not yet spoken."""

    translation: str
    verified: bool
    facts: list[StoredFact]


@dataclass
class VoiceProgress:
    texts: dict[str, PendingText] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)


def load_progress(bundle_dir: Path) -> VoiceProgress:
    try:
        raw = json.loads((bundle_dir / PROGRESS_NAME).read_text("utf-8"))
        texts = {key: PendingText(**item) for key, item in raw["texts"].items()}
        return VoiceProgress(texts, dict(raw["failures"]))
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        return VoiceProgress()


def _save_progress(bundle_dir: Path, progress: VoiceProgress) -> None:
    body = {
        "texts": {key: text.model_dump() for key, text in progress.texts.items()},
        "failures": progress.failures,
    }
    write_json(bundle_dir / PROGRESS_NAME, body)


# --- what is missing ---------------------------------------------------------------------------


def picker_pairs(clips_dir: Path, bundle_dir: Path) -> list[Pair]:
    """Every (picker clip, rider language other than its own) that the bundle can transcribe.

    The picker is demo/clips/manifest.json. A clip's transcript is the one already stored for it
    in the bundle; a clip with no stored transcript has nothing to translate and is left out."""
    try:
        listed = json.loads((clips_dir / MANIFEST_NAME).read_text("utf-8"))["clips"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    turns = read_turns(bundle_dir)
    pairs: list[Pair] = []
    for entry in listed:
        wav = clips_dir / f"{entry['id']}.wav"
        if not wav.is_file():
            continue
        sha = clip_digest(wav.read_bytes())
        transcript = next(
            (t.transcript for t in turns if t.clip_sha256 == sha and t.src == entry["lang"]), None
        )
        if transcript is None:
            continue
        pairs += [
            Pair(entry["id"], sha, entry["lang"], tgt, transcript)
            for tgt in LANGUAGES
            if tgt != entry["lang"]
        ]
    return pairs


def _has_audio(pair: Pair, bundle_dir: Path, turns: Sequence[BundleTurn]) -> bool:
    return any(
        (t.clip_sha256, t.src, t.tgt) == (pair.sha, pair.src, pair.tgt)
        and (bundle_dir / t.audio).is_file()
        for t in turns
    )


def missing_pairs(pairs: Sequence[Pair], bundle_dir: Path) -> list[Pair]:
    """The pairs with no stored audio: each costs one text-to-speech call."""
    turns = read_turns(bundle_dir)
    return [pair for pair in pairs if not _has_audio(pair, bundle_dir, turns)]


def turns_without_facts(bundle_dir: Path) -> int:
    return sum(1 for turn in read_turns(bundle_dir) if turn.facts is None)


def new_turns_per_language(missing: Sequence[Pair]) -> dict[str, int]:
    return {tgt: sum(1 for p in missing if p.tgt == tgt) for tgt in LANGUAGES}


# --- the build ---------------------------------------------------------------------------------


class Speech(Protocol):
    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes: ...


@dataclass
class VoiceReport:
    stored: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)  # failed on an earlier run, not retried
    facts_added: int = 0


def attach_missing_facts(bundle_dir: Path, translator: Translator) -> int:
    """Give every stored turn that predates stored facts its facts. Free: no Gnani call, and the
    stored translation and audio stay as they are."""
    turns = read_turns(bundle_dir)
    added = 0
    for turn in turns:
        if turn.facts is not None:
            continue
        facts = tuple(extract_facts(turn.transcript, turn.src))
        facts = localize_landmarks(facts, turn.src, turn.tgt, translator)
        turn.facts = [StoredFact.of(fact) for fact in facts]
        added += 1
    if added:
        write_turns(bundle_dir, turns)
    return added


def _reason(exc: Exception) -> str:
    """The kind of failure and the HTTP status only, never a message that could quote speech."""
    if isinstance(exc, GnaniError):
        return f"gnani status {exc.status}" if exc.status else "gnani unreachable"
    return type(exc).__name__


async def _text_for(pair: Pair, progress: VoiceProgress, translator: Translator) -> PendingText:
    pending = progress.texts.get(pair.key)
    if pending is None:
        facts, translation, verified = await translate_transcript(
            pair.transcript, pair.src, pair.tgt, translator
        )
        pending = PendingText(
            translation=translation,
            verified=verified,
            facts=[StoredFact.of(fact) for fact in facts],
        )
        progress.texts[pair.key] = pending
    return pending


async def build_voices(
    missing: Sequence[Pair],
    bundle_dir: Path,
    gnani: Speech,
    translator: Translator,
    *,
    retry_failed: bool = False,
    say: Callable[[str], None] = print,
) -> VoiceReport:
    """Translate (once), speak and store each missing pair. A Gnani failure is recorded and the run
    moves on; an exhausted budget stops it. Progress is saved after every paid call."""
    report = VoiceReport()
    report.facts_added = attach_missing_facts(bundle_dir, translator)
    progress = load_progress(bundle_dir)
    turns = read_turns(bundle_dir)
    try:
        for pair in missing:
            if pair.key in progress.failures and not retry_failed:
                report.skipped.append(pair.key)
                continue
            progress.failures.pop(pair.key, None)
            try:
                text = await _text_for(pair, progress, translator)
                _save_progress(bundle_dir, progress)  # the translation is kept before it is spoken
                if not text.translation.strip():
                    raise EmptyTranslationError
                target = LANGUAGES[pair.tgt]
                audio = await gnani.synthesize(
                    text.translation, target.gnani_code, target.tts_voice
                )
            except (GnaniError, TranslationUnavailableError, EmptyTranslationError) as exc:
                reason = _reason(exc)
                progress.failures[pair.key] = reason
                report.failed[pair.key] = reason
                say(f"  FAILED {pair.key}: {reason}")
                _save_progress(bundle_dir, progress)
                continue
            (bundle_dir / pair.audio_name).write_bytes(audio)
            turns.append(
                BundleTurn(
                    clip_sha256=pair.sha,
                    src=pair.src,
                    tgt=pair.tgt,
                    transcript=pair.transcript,
                    translation=text.translation,
                    verified=text.verified,
                    audio=pair.audio_name,
                    facts=text.facts,
                )
            )
            write_turns(bundle_dir, turns)
            del progress.texts[pair.key]
            _save_progress(bundle_dir, progress)
            report.stored.append(pair.key)
            say(f"  stored {pair.key}")
    except BudgetExceededError:
        _save_progress(bundle_dir, progress)
        raise
    return report
