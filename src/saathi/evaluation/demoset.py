"""The guided-demo clip set: the committed manifest, the resumable paid build, and the comparison
of expected facts with what the speech recogniser actually wrote.

demo/clip_set.json holds, for every clip, the source text, the facts the card should show and the
rider language it is recorded for. The build turns each new clip into a bundle turn with three paid
calls (customer speech, transcription, rider speech) and never repeats a step that already
succeeded, so a stopped run costs nothing twice.
"""

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator

from saathi.demobundle import BUNDLE_NAME, BUNDLE_VERSION, BundleTurn
from saathi.evaluation import noisemix
from saathi.evaluation.calls import BudgetExceededError
from saathi.evaluation.democlips import mix_clip
from saathi.facts import Fact, FactKind, extract_facts
from saathi.facts.text import key
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES
from saathi.pipeline import (
    AUDIO_FILENAME,
    NoSpeechError,
    TranslationUnavailableError,
    UnreliableTranslationError,
    translate_transcript,
)
from saathi.translate import Translator

CLIP_SET_VERSION = 1
PROGRESS_NAME = "progress.json"
MANIFEST_NAME = "manifest.json"
CALLS_PER_NEW_CLIP = 3  # customer speech, transcription, rider speech

ClipType = Literal["street", "apartment", "correction", "mixed", "landmark"]
CLIP_TYPES: tuple[ClipType, ...] = ("street", "apartment", "correction", "mixed", "landmark")
ReviewStatus = Literal["for author review", "machine-written, not reviewed"]
Step = Literal["tts", "stt", "rider"]


class ExpectedFact(BaseModel, frozen=True):
    kind: FactKind
    value: str


class SetClip(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    lang: str
    type: ClipType
    text: str = Field(min_length=1)
    expected: list[ExpectedFact]  # what the card should show after this clip
    tgt: str  # the one rider language this clip is recorded for
    review_status: ReviewStatus
    label: str
    label_local: str = ""
    existing: bool = False  # recorded earlier: kept as it is, never rebuilt
    note: str = ""

    @field_validator("lang", "tgt")
    @classmethod
    def _known_language(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError(f"unknown language {value!r}")
        return value

    @model_validator(mode="after")
    def _pair_differs(self) -> "SetClip":
        if self.lang == self.tgt:
            raise ValueError("a clip cannot be recorded for its own language")
        return self


class ClipSet(BaseModel):
    version: int
    clips: list[SetClip]

    @model_validator(mode="after")
    def _shape(self) -> "ClipSet":
        if self.version != CLIP_SET_VERSION:
            raise ValueError("unsupported clip set version")
        ids = [clip.id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate clip id")
        return self


def load_clip_set(path: Path) -> list[SetClip]:
    return ClipSet.model_validate_json(path.read_text("utf-8")).clips


def set_problems(clips: Sequence[SetClip]) -> list[str]:
    """Ways the set misses the brief: five clips per language, one of each type, every language a
    rider target. Empty when the set is complete."""
    problems: list[str] = []
    for lang in LANGUAGES:
        types = sorted(clip.type for clip in clips if clip.lang == lang)
        if types != sorted(CLIP_TYPES):
            problems.append(f"{lang}: clip types are {types}")
    missing = sorted(set(LANGUAGES) - {clip.tgt for clip in clips})
    if missing:
        problems.append(f"never a rider language: {', '.join(missing)}")
    return problems


# --- progress and the bundle on disk -----------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    clips_dir: Path
    bundle_dir: Path

    def wav(self, clip: SetClip) -> Path:
        return self.clips_dir / f"{clip.id}.wav"

    def rider_wav_name(self, clip: SetClip) -> str:
        return f"{clip.id}-{clip.tgt}.wav"


@dataclass
class Progress:
    """What has been paid for but is not yet in the bundle (transcripts), and what failed."""

    transcripts: dict[str, str] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)


def _write_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(body, ensure_ascii=False, indent=2), "utf-8")
    os.replace(temporary, path)


def load_progress(bundle_dir: Path) -> Progress:
    try:
        raw = json.loads((bundle_dir / PROGRESS_NAME).read_text("utf-8"))
        return Progress(dict(raw["transcripts"]), dict(raw["failures"]))
    except (OSError, ValueError, KeyError, TypeError):
        return Progress()


def _save_progress(bundle_dir: Path, progress: Progress) -> None:
    body = {"transcripts": progress.transcripts, "failures": progress.failures}
    _write_json(bundle_dir / PROGRESS_NAME, body)


def read_turns(bundle_dir: Path) -> list[BundleTurn]:
    try:
        raw = json.loads((bundle_dir / BUNDLE_NAME).read_text("utf-8"))
        return [BundleTurn(**item) for item in raw["turns"]]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _write_turns(bundle_dir: Path, turns: Sequence[BundleTurn]) -> None:
    body = {"version": BUNDLE_VERSION, "turns": [turn.model_dump() for turn in turns]}
    _write_json(bundle_dir / BUNDLE_NAME, body)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _find_turn(turns: Sequence[BundleTurn], sha: str, clip: SetClip) -> BundleTurn | None:
    for turn in turns:
        if (turn.clip_sha256, turn.src, turn.tgt) == (sha, clip.lang, clip.tgt):
            return turn
    return None


def pending_steps(
    clip: SetClip, layout: Layout, progress: Progress, turns: Sequence[BundleTurn]
) -> list[Step]:
    """The paid steps this clip still needs. Empty for an existing clip or a finished one."""
    if clip.existing:
        return []
    wav = layout.wav(clip)
    if not wav.is_file():
        return ["tts", "stt", "rider"]
    sha = _sha(wav.read_bytes())
    if _find_turn(turns, sha, clip) is not None:
        return []
    heard = clip.id in progress.transcripts or any(
        t.clip_sha256 == sha and t.src == clip.lang for t in turns
    )
    return ["rider"] if heard else ["stt", "rider"]


def planned_calls(
    clips: Sequence[SetClip], layout: Layout, progress: Progress, retry_failed: bool = False
) -> int:
    turns = read_turns(layout.bundle_dir)
    return sum(
        len(pending_steps(clip, layout, progress, turns))
        for clip in clips
        if retry_failed or clip.id not in progress.failures
    )


# --- the build ---------------------------------------------------------------------------------


class Speech(Protocol):
    async def transcribe(self, audio: bytes, filename: str, language_code: str) -> str: ...

    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes: ...


@dataclass
class BuildReport:
    built: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)  # failed on an earlier run, not retried


async def build_set(
    clips: Sequence[SetClip],
    gnani: Speech,
    translator: Translator,
    noise: noisemix.Samples,
    layout: Layout,
    seed: int,
    *,
    retry_failed: bool = False,
    say: Callable[[str], None] = print,
) -> BuildReport:
    """Run every missing step for every clip. A Gnani failure is recorded and the run moves on to
    the next clip; running out of budget stops it. Progress is saved after each paid step."""
    report = BuildReport()
    progress = load_progress(layout.bundle_dir)
    turns = read_turns(layout.bundle_dir)
    try:
        for clip in clips:
            if clip.id in progress.failures and not retry_failed:
                report.skipped.append(clip.id)
                continue
            if not pending_steps(clip, layout, progress, turns):
                continue
            progress.failures.pop(clip.id, None)
            try:
                await _build_clip(clip, gnani, translator, noise, layout, seed, progress, turns)
                report.built.append(clip.id)
                say(f"  built {clip.id}")
            except (
                GnaniError,
                NoSpeechError,
                TranslationUnavailableError,
                UnreliableTranslationError,
            ) as exc:
                reason = _reason(exc)
                progress.failures[clip.id] = reason
                report.failed[clip.id] = reason
                say(f"  FAILED {clip.id}: {reason}")
            _save_progress(layout.bundle_dir, progress)
    except BudgetExceededError:
        _save_progress(layout.bundle_dir, progress)
        raise
    return report


def _reason(exc: Exception) -> str:
    """Only the kind of failure and the HTTP status, never a message that could quote speech."""
    if isinstance(exc, GnaniError):
        return f"gnani status {exc.status}" if exc.status else "gnani unreachable"
    return type(exc).__name__


async def _build_clip(
    clip: SetClip,
    gnani: Speech,
    translator: Translator,
    noise: noisemix.Samples,
    layout: Layout,
    seed: int,
    progress: Progress,
    turns: list[BundleTurn],
) -> None:
    src, tgt = LANGUAGES[clip.lang], LANGUAGES[clip.tgt]
    wav = layout.wav(clip)
    if not wav.is_file():
        spoken = await gnani.synthesize(clip.text, src.gnani_code, src.tts_voice)
        layout.clips_dir.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(mix_clip(spoken, noise, seed, clip.id))
    audio = wav.read_bytes()
    sha = _sha(audio)

    transcript = progress.transcripts.get(clip.id) or next(
        (t.transcript for t in turns if t.clip_sha256 == sha and t.src == clip.lang), ""
    )
    if not transcript:
        transcript = (await gnani.transcribe(audio, AUDIO_FILENAME, src.gnani_code)).strip()
        if not transcript:
            raise NoSpeechError
        progress.transcripts[clip.id] = transcript
        _save_progress(layout.bundle_dir, progress)

    _facts, translation, verified = await translate_transcript(
        transcript, clip.lang, clip.tgt, translator
    )
    speech = await gnani.synthesize(translation, tgt.gnani_code, tgt.tts_voice)
    name = layout.rider_wav_name(clip)
    layout.bundle_dir.mkdir(parents=True, exist_ok=True)
    (layout.bundle_dir / name).write_bytes(speech)
    turns.append(
        BundleTurn(
            clip_sha256=sha,
            src=clip.lang,
            tgt=clip.tgt,
            transcript=transcript,
            translation=translation,
            verified=verified,
            audio=name,
        )
    )
    _write_turns(layout.bundle_dir, turns)


def write_manifest(clips: Sequence[SetClip], layout: Layout) -> list[str]:
    """demo/clips/manifest.json for the clips worth showing: the wav exists, the bundle holds a turn
    for it, and the facts read from that turn's stored transcript are exactly the expected ones.
    A clip the speech recogniser got wrong stays in the eval set but not in the picker.
    Returns the ids written."""
    turns = read_turns(layout.bundle_dir)
    entries: list[dict[str, str]] = []
    for clip in clips:
        wav = layout.wav(clip)
        if not wav.is_file():
            continue
        sha = _sha(wav.read_bytes())
        stored = next((t for t in turns if t.clip_sha256 == sha and t.src == clip.lang), None)
        if stored is not None and not compare_facts(
            clip.expected, extract_facts(stored.transcript, clip.lang)
        ):
            entries.append(
                {
                    "id": clip.id,
                    "lang": clip.lang,
                    "label": clip.label,
                    "label_local": clip.label_local,
                }
            )
    _write_json(layout.clips_dir / MANIFEST_NAME, {"clips": entries})
    return [entry["id"] for entry in entries]


# --- comparing expected facts with what was heard ----------------------------------------------


def _norm(text: str) -> str:
    return " ".join(key(token) for token in text.split())


def _same_landmark(expected: str, heard: str) -> bool:
    a, b = _norm(expected), _norm(heard)
    return bool(a) and bool(b) and (a in b or b in a)


def compare_facts(expected: Sequence[ExpectedFact], heard: Sequence[Fact]) -> list[str]:
    """Differences between the expected card and the facts read from the transcript; empty = MATCH.

    Structured facts follow the card's rule (the last value of a kind wins, so a spoken correction
    replaces the mistake) and must agree exactly, with no extra kind. Landmarks are open
    vocabulary: each expected name must be found and each heard name must be an expected one.
    """
    differences: list[str] = []
    latest: dict[str, str] = {}
    for fact in heard:
        if fact.kind != "landmark":
            latest[str(fact.kind)] = fact.value
    wanted: dict[str, str] = {e.kind: e.value for e in expected if e.kind != "landmark"}
    for kind in sorted(set(wanted) | set(latest)):
        if wanted.get(kind) != latest.get(kind):
            differences.append(f"{kind}: expected {wanted.get(kind)}, heard {latest.get(kind)}")
    expected_marks = [e.value for e in expected if e.kind == "landmark"]
    heard_marks = [f.value for f in heard if f.kind == "landmark"]
    differences += [
        f"landmark missing: {name}"
        for name in expected_marks
        if not any(_same_landmark(name, h) for h in heard_marks)
    ]
    differences += [
        f"landmark extra: {name}"
        for name in heard_marks
        if not any(_same_landmark(e, name) for e in expected_marks)
    ]
    return differences
