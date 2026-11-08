"""The language matrix: every ordered pair of the ten languages through the guided demo.

For each customer language A and each other language B, the verified clips of A are sent, as the
customer, to a rider who chose B. The route is the one a phone uses (POST /rooms/{code}/turn with
the demo-clip header), the bundle is the shipped one and the translator is the real local
IndicTrans2. Gnani is a stand-in that refuses any use, so a run makes no Gnani call.

This module holds what needs no model: which clips count, what is checked on a turn and how the
result is written up. scripts/language_matrix.py wires it to the real app and writes the files.
"""

import asyncio
import math
import statistics
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import BaseModel

from saathi.demobundle import clip_digest
from saathi.evaluation.demoset import (
    MANIFEST_NAME,
    ExpectedFact,
    Layout,
    Step,
    compare_facts,
    load_clip_set,
    load_progress,
    pending_steps,
    read_turns,
)
from saathi.facts.types import FACT_KINDS, Fact, FactKind
from saathi.languages import LANGUAGES
from saathi.rooms import Event, RoomManager

WAV_HEADER_BYTES = 44  # a RIFF/WAVE header alone is 44 bytes: a file this small plays nothing


class GnaniForbidden:
    """Stands in for the Gnani client. Any use is counted and refused, so a run that reached for
    Gnani fails loudly and the report can state that it made no call."""

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def __getattr__(self, name: str) -> Any:
        self.attempts.append(name)
        raise AssertionError(f"Gnani was touched: {name}")


# --- the clips that count -----------------------------------------------------------------------


class _ManifestEntry(BaseModel):
    id: str


class _Manifest(BaseModel):
    clips: list[_ManifestEntry]


@dataclass(frozen=True)
class MatrixClip:
    id: str
    lang: str
    wav: bytes
    expected: tuple[ExpectedFact, ...]
    # Rider languages the bundle holds a stored translation and audio for. Any other rider
    # language gets the text-only fallback, by design.
    recorded_for: frozenset[str]


def load_matrix_clips(
    clip_set_path: Path, clips_dir: Path, bundle_dir: Path
) -> tuple[list[MatrixClip], list[str]]:
    """The verified clips, and the ids of the set's clips that are left out.

    Verified means listed in the picker manifest: the wav exists, the bundle holds a turn for it
    and the facts read from that turn's stored transcript are exactly the expected ones.
    """
    clip_set = load_clip_set(clip_set_path)
    manifest = _Manifest.model_validate_json((clips_dir / MANIFEST_NAME).read_text("utf-8"))
    listed = {entry.id for entry in manifest.clips}
    unknown = listed - {clip.id for clip in clip_set}
    if unknown:
        raise ValueError(f"the manifest lists clips that are not in the set: {sorted(unknown)}")
    layout = Layout(clips_dir, bundle_dir)
    turns = read_turns(bundle_dir)
    clips: list[MatrixClip] = []
    left_out: list[str] = []
    for clip in clip_set:
        if clip.id not in listed:
            left_out.append(clip.id)
            continue
        wav = layout.wav(clip).read_bytes()
        digest = clip_digest(wav)
        recorded = frozenset(
            turn.tgt for turn in turns if turn.clip_sha256 == digest and turn.src == clip.lang
        )
        clips.append(MatrixClip(clip.id, clip.lang, wav, tuple(clip.expected), recorded))
    return clips, left_out


# --- the Gnani mapping, from what the last real build stored ------------------------------------

STEP_NAMES: dict[Step, str] = {
    "tts": "customer speech",
    "stt": "transcription",
    "rider": "rider speech",
}


@dataclass(frozen=True)
class MappingRow:
    lang: str
    stt_code: str
    voice: str
    clips: int  # clips of this language that the build had to make
    speech_made: int  # of those, with a stored customer recording (Timbre, this voice)
    transcribed: int  # of those, with a stored transcript (Prisma, this code)
    rider_clips: int  # clips of the build that were recorded for this rider language
    rider_made: int  # of those, with a stored rider recording (Timbre, this voice)


@dataclass(frozen=True)
class MappingEvidence:
    rows: tuple[MappingRow, ...] = ()
    failures: tuple[str, ...] = ()  # clips that stopped before all three calls were stored
    earlier: tuple[str, ...] = ()  # clips an earlier build recorded; not counted


def mapping_evidence(clip_set_path: Path, clips_dir: Path, bundle_dir: Path) -> MappingEvidence:
    """What the last real build stored for each language's Gnani code and voice.

    A clip costs three calls: its speech in its own language's voice, its transcript in that
    language's code and the rider's speech in the rider language's voice. Which of them are stored
    is read from the files in demo/, by the build's own rule (pending_steps), so no call is made.
    """
    layout, progress = Layout(clips_dir, bundle_dir), load_progress(bundle_dir)
    turns = read_turns(bundle_dir)
    clip_set = load_clip_set(clip_set_path)
    built = [clip for clip in clip_set if not clip.existing]
    made, heard, rider = Counter[str](), Counter[str](), Counter[str]()
    failures: list[str] = []
    for clip in built:
        pending = pending_steps(clip, layout, progress, turns)
        if "rider" not in pending and not (bundle_dir / layout.rider_wav_name(clip)).is_file():
            pending.append("rider")  # the bundle loader skips a turn whose audio file is missing
        if "tts" not in pending:
            made[clip.lang] += 1
        if "stt" not in pending:
            heard[clip.lang] += 1
        if "rider" not in pending:
            rider[clip.tgt] += 1
        if pending:
            reason = progress.failures.get(clip.id, "no failure recorded")
            failures.append(
                f"`{clip.id}` ({clip.lang}): {reason}; "
                f"first call not stored: {STEP_NAMES[pending[0]]}"
            )
    rows = tuple(
        MappingRow(
            lang=code,
            stt_code=language.gnani_code,
            voice=language.tts_voice,
            clips=sum(1 for clip in built if clip.lang == code),
            speech_made=made[code],
            transcribed=heard[code],
            rider_clips=sum(1 for clip in built if clip.tgt == code),
            rider_made=rider[code],
        )
        for code, language in sorted(LANGUAGES.items())
    )
    earlier = tuple(clip.id for clip in clip_set if clip.existing)
    return MappingEvidence(rows, tuple(failures), earlier)


# --- what one replayed turn looked like, and what is checked ------------------------------------


@dataclass(frozen=True)
class Seen:
    """One replayed turn as both screens saw it."""

    status: int
    ms: float
    error_code: str = ""
    rider_event: bool = False  # the rider's event stream carried this turn
    customer_facts: tuple[Mapping[str, Any], ...] = ()
    rider_facts: tuple[Mapping[str, Any], ...] = ()
    translation: str = ""
    verified: bool = False
    audio_path: str | None = None
    audio_status: int | None = None
    audio_playable: bool = False


@dataclass(frozen=True)
class ClipRun:
    clip_id: str
    src: str
    tgt: str
    ms: float
    stored_audio: bool  # False: the rider got the text-only fallback
    verified: bool  # the translation passed the placeholder check, as the rider's screen shows it
    landmark_chips: int
    landmarks_localised: int  # landmark chips that carry a rendering in the rider's language
    problems: tuple[str, ...]  # empty = the replay passed


def is_wav(data: bytes) -> bool:
    return len(data) > WAV_HEADER_BYTES and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def shown_differences(
    expected: Sequence[ExpectedFact], shown: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Differences between the expected card and the chips a screen showed; empty = they agree.

    It applies the demo set's own rule (compare_facts), so a clip counts as correct here exactly
    when it counts as MATCH in eval/results/demo_set_after_fixes.md.
    """
    heard: list[Fact] = []
    for chip in shown:
        kind, value = chip.get("kind"), chip.get("value")
        if kind not in FACT_KINDS or not isinstance(value, str):
            return [f"a chip is malformed: {dict(chip)}"]
        heard.append(Fact(cast(FactKind, kind), value, 0, 0, str(chip.get("heard", ""))))
    return compare_facts(expected, heard)


def landmark_counts(chips: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    """(landmark chips, those with a rendering in the viewer's language)"""
    landmarks = [chip for chip in chips if chip.get("kind") == "landmark"]
    return len(landmarks), sum(1 for chip in landmarks if chip.get("local"))


def check_turn(clip: MatrixClip, tgt: str, seen: Seen) -> list[str]:
    """Why this replay failed; empty = it passed."""
    if seen.status != 200:
        return [f"the turn was refused with HTTP {seen.status} {seen.error_code}".rstrip()]
    if not seen.rider_event:
        return ["the rider's screen received no turn"]
    problems = [
        f"customer chips: {line}" for line in shown_differences(clip.expected, seen.customer_facts)
    ]
    problems += [
        f"rider chips: {line}" for line in shown_differences(clip.expected, seen.rider_facts)
    ]
    if any(not str(chip.get("label", "")).strip() for chip in seen.rider_facts):
        problems.append("a rider chip has no label")
    if not seen.translation.strip():
        problems.append("the translation is empty")
    recorded = tgt in clip.recorded_for
    if recorded and seen.audio_path is None:
        problems.append("stored audio was recorded for this pair but the rider got text only")
    if not recorded and seen.audio_path is not None:
        problems.append("no audio was recorded for this pair but the rider was offered some")
    if seen.audio_path is not None and not seen.audio_playable:
        problems.append(f"the stored audio did not load as a WAV (HTTP {seen.audio_status})")
    return problems


# --- driving the real route ---------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _error_code(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return ""
    if isinstance(detail, dict):
        return str(detail.get("code", ""))
    return str(detail or "")


def _turn_event(queue: asyncio.Queue[Event | None], turn_id: str) -> Event | None:
    """Empty the rider's queue and return its event for this turn (the card event follows it)."""
    found: Event | None = None
    while True:
        try:
            event = queue.get_nowait()
        except asyncio.QueueEmpty:
            return found
        if event is not None and event.name == "turn" and event.data.get("turn_id") == turn_id:
            found = event


async def _observe(
    client: httpx.AsyncClient,
    queue: asyncio.Queue[Event | None],
    rider_token: str,
    response: httpx.Response,
    ms: float,
) -> Seen:
    if response.status_code != 200:
        return Seen(response.status_code, ms, error_code=_error_code(response))
    body = response.json()
    customer_facts = tuple(body["facts"])
    event = _turn_event(queue, body["turn_id"])
    if event is None:
        return Seen(200, ms, customer_facts=customer_facts)
    audio_path: str | None = event.data.get("audio_path")
    audio_status: int | None = None
    playable = False
    if audio_path is not None:
        audio = await client.get(audio_path, headers=_auth(rider_token))
        audio_status = audio.status_code
        playable = audio.status_code == 200 and is_wav(audio.content)
    return Seen(
        200,
        ms,
        rider_event=True,
        customer_facts=customer_facts,
        rider_facts=tuple(event.data["facts"]),
        translation=str(event.data["translation"]),
        verified=bool(event.data["verified"]),
        audio_path=audio_path,
        audio_status=audio_status,
        audio_playable=playable,
    )


async def _play_clip(
    client: httpx.AsyncClient,
    queue: asyncio.Queue[Event | None],
    code: str,
    tokens: tuple[str, str],
    clip: MatrixClip,
    tgt: str,
) -> ClipRun:
    customer_token, rider_token = tokens
    started = time.perf_counter()
    try:
        response = await client.post(
            f"/rooms/{code}/turn",
            files={"audio": (f"{clip.id}.wav", clip.wav, "audio/wav")},
            headers={**_auth(customer_token), "X-Demo-Clip": "1"},
        )
        ms = (time.perf_counter() - started) * 1000.0
        seen = await _observe(client, queue, rider_token, response, ms)
    except Exception as exc:
        # Any failure of one replay is the finding for that cell, written to the report with its
        # type and message; the other pairs still run.
        ms = (time.perf_counter() - started) * 1000.0
        problem = f"exception: {type(exc).__name__}: {exc}"
        return ClipRun(clip.id, clip.lang, tgt, ms, False, False, 0, 0, (problem,))
    chips, localised = landmark_counts(seen.rider_facts)
    return ClipRun(
        clip.id,
        clip.lang,
        tgt,
        seen.ms,
        seen.audio_path is not None,
        seen.verified,
        chips,
        localised,
        tuple(check_turn(clip, tgt, seen)),
    )


async def _run_pair(
    client: httpx.AsyncClient,
    manager: RoomManager,
    clips: Sequence[MatrixClip],
    src: str,
    tgt: str,
) -> list[ClipRun]:
    created = await client.post("/rooms", json={"language": src})
    created.raise_for_status()
    code, customer_token = created.json()["code"], created.json()["token"]
    joined = await client.post(f"/rooms/{code}/join", json={"language": tgt})
    joined.raise_for_status()
    rider_token = joined.json()["token"]
    room = manager.authorize(code, rider_token).room
    queue = manager.subscribe(room, "rider")
    try:
        return [
            await _play_clip(client, queue, code, (customer_token, rider_token), clip, tgt)
            for clip in clips
        ]
    finally:
        manager.close(room)


async def run_matrix(
    client: httpx.AsyncClient,
    manager: RoomManager,
    clips: Sequence[MatrixClip],
    languages: Sequence[str],
    progress: Callable[[str], None] | None = None,
) -> list[ClipRun]:
    """Play every verified clip of each language to a rider of every other language."""
    by_language = {lang: [clip for clip in clips if clip.lang == lang] for lang in languages}
    missing = [lang for lang, found in by_language.items() if not found]
    if missing:
        raise ValueError(f"no verified clip for: {', '.join(missing)}")
    runs: list[ClipRun] = []
    for src in languages:
        for tgt in languages:
            if tgt == src:
                continue
            pair = await _run_pair(client, manager, by_language[src], src, tgt)
            runs.extend(pair)
            if progress is not None:
                failed = sum(1 for run in pair if run.problems)
                progress(f"{src} -> {tgt}: {len(pair) - failed}/{len(pair)} clips passed")
    return runs


# --- the report ---------------------------------------------------------------------------------


def _percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile of a non-empty sequence."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def _cell(runs: Sequence[ClipRun]) -> str:
    if not runs:
        return "n/a"
    verdict = "FAIL" if any(run.problems for run in runs) else "ok"
    return f"{verdict} {round(statistics.median(run.ms for run in runs))}"


def _timing_row(label: str, runs: Sequence[ClipRun]) -> str:
    if not runs:
        return f"| {label} | 0 | - | - | - |"
    times = [run.ms for run in runs]
    median, p95, worst = statistics.median(times), _percentile(times, 0.95), max(times)
    return f"| {label} | {len(runs)} | {median:.0f} | {p95:.0f} | {worst:.0f} |"


def pair_failures(runs: Sequence[ClipRun]) -> dict[tuple[str, str], list[ClipRun]]:
    """The failed replays of each failing ordered pair."""
    failing: dict[tuple[str, str], list[ClipRun]] = {}
    for run in runs:
        if run.problems:
            failing.setdefault((run.src, run.tgt), []).append(run)
    return failing


def render_report(
    runs: Sequence[ClipRun],
    *,
    languages: Sequence[str],
    meta: Mapping[str, Any],
    left_out: Sequence[str],
    gnani_attempts: int,
    mapping: MappingEvidence | None = None,
) -> str:
    codes = sorted(languages)
    pairs = [(src, tgt) for src in codes for tgt in codes if src != tgt]
    failing = pair_failures(runs)
    failed_runs = sum(1 for run in runs if run.problems)
    stored = [run for run in runs if run.stored_audio]
    text_only = [run for run in runs if not run.stored_audio]
    clip_count = len({run.clip_id for run in runs})

    lines = [
        f"# Language matrix: {len(pairs)} ordered pairs through the guided demo",
        "",
        f"Run {meta.get('started_utc', 'unknown')} on {meta.get('device', 'unknown')} "
        f"({meta.get('power_state', 'unknown')} power), "
        f"commit {meta.get('git_commit', 'unknown')}, torch {meta.get('torch', 'unknown')}, "
        f"IndicTrans2 with {meta.get('num_beams', '?')} beam(s). "
        "Produced by `scripts/language_matrix.py`.",
        "",
        "## Result",
        "",
        f"- {len(pairs) - len(failing)} of {len(pairs)} ordered pairs passed. A pair passes when "
        "every verified clip of the customer's language passed.",
        f"- Clip replays: {len(runs)}, from {clip_count} verified clips. "
        f"{len(runs) - failed_runs} passed, {failed_runs} failed.",
        f"- Gnani calls made by this run: {gnani_attempts}. The client the app was given refuses "
        "any use, and `.env` was not read.",
        f"- Replays where the rider got stored audio: {len(stored)}; the text-only fallback: "
        f"{len(text_only)}. Every pair in `demo/bundle` has a stored translation, facts and "
        "audio; a text-only replay means a pair is missing from the bundle.",
        "",
        "## Matrix",
        "",
        "Rows are the customer's language, columns the rider's. Each cell is the result and the "
        "median response time in ms over that pair's clips; `n/a` is the same language twice, "
        "which a room refuses.",
        "",
        "| from \\ to | " + " | ".join(codes) + " |",
        "|---|" + "---|" * len(codes),
    ]
    for src in codes:
        row = [_cell([run for run in runs if run.src == src and run.tgt == tgt]) for tgt in codes]
        lines.append(f"| {src} | " + " | ".join(row) + " |")

    lines += ["", "## Failures", ""]
    if not failing:
        lines.append("None: every replay passed.")
    for (src, tgt), failed in failing.items():
        for run in failed:
            lines.append(f"- `{src}` to `{tgt}`, clip `{run.clip_id}`: " + "; ".join(run.problems))

    lines += [
        "",
        "## Response time",
        "",
        "Wall-clock time of the one POST, in ms. A stored pair is a lookup: translation, facts and "
        "audio are read from the bundle. A pair missing from the bundle runs the real local "
        "translator.",
        "",
        "| path | replays | median | 95th percentile | slowest |",
        "|---|---|---|---|---|",
        _timing_row("stored translation and audio", stored),
        _timing_row("local translation, text only", text_only),
        "",
        "This is a correctness run, not a benchmark: nothing was done to quiet the machine, so "
        "these times show what a laptop in ordinary use did, not what the app can do. Latency "
        "under stated conditions is in `eval/results/latency.json`.",
        "",
        "## By rider language",
        "",
        "A translation counts as verified when every number and loanword placeholder came back "
        "from the model exactly once. When one did not, the rider gets the facts spelled out from "
        "tables instead of the model's sentence, and the delivery card is unaffected. Stored "
        "pairs are counted with the flag recorded when they were built.",
        "",
        "Landmark chips are the open-vocabulary facts; one with no rendering in the rider's "
        "language is shown as it was heard.",
        "",
        "| rider | replays | translation not verified | landmark chips | with a rendering |",
        "|---|---|---|---|---|",
    ]
    for tgt in codes:
        mine = [run for run in runs if run.tgt == tgt]
        unverified = sum(1 for run in mine if not run.verified)
        chips = sum(run.landmark_chips for run in mine)
        localised = sum(run.landmarks_localised for run in mine)
        lines.append(f"| {tgt} | {len(mine)} | {unverified} | {chips} | {localised} |")

    lines += [
        "",
        "## What was checked",
        "",
        "Each replay is one `POST /rooms/{code}/turn` with the demo-clip header, made in process "
        "against the application in public mode with the shipped bundle and the real local "
        "translator (after the warm-up the app does at start). It passes when:",
        "",
        "- the turn is accepted and raises no exception;",
        "- the chips on the customer's screen and on the rider's screen equal the clip's expected "
        "facts, by the rule the demo-set scoring uses, and every rider chip has a label;",
        "- the translation is not empty;",
        "- the rider gets stored audio that loads as a WAV when the bundle holds one for that "
        "pair (all of them should), and the text-only fallback otherwise.",
        "",
        "A verified clip is one listed in `demo/clips/manifest.json`: its stored transcript "
        "yields exactly the expected facts. Speech recognition and synthesis are not run (the "
        "transcripts and audio are stored), so this does not test how a person's voice is heard.",
    ]
    if left_out:
        lines += [
            "",
            f"{len(left_out)} clips of the 50-clip set are not in the manifest and are not "
            "replayed (see `eval/results/demo_set_after_fixes.md` for each): "
            + ", ".join(f"`{clip_id}`" for clip_id in left_out)
            + ".",
        ]
    if mapping is not None:
        lines += _mapping_lines(mapping)
    return "\n".join(lines) + "\n"


def _mapping_lines(mapping: MappingEvidence) -> list[str]:
    lines = [
        "",
        "## Gnani language mapping",
        "",
        "Each language's speech-to-text code (Prisma) and text-to-speech voice (Timbre) are in "
        "`src/saathi/languages.py`. The columns count what the 50-clip build "
        "(`scripts/build_demo_set.py`) stored for each language: the customer clip is Timbre "
        "speech in the clip's language and voice, the transcript is Prisma output for that "
        "language's code, and the rider recording is Timbre speech in the rider language's voice. "
        "They are counted from the files in `demo/`, the way the build decides what is missing; "
        "no call was made to produce this table.",
        "",
        "| language | speech-to-text code | voice | customer speech | transcribed | rider speech |",
        "|---|---|---|---|---|---|",
    ]
    for row in mapping.rows:
        lines.append(
            f"| {row.lang} | {row.stt_code} | {row.voice} | {row.speech_made} of {row.clips} "
            f"| {row.transcribed} of {row.clips} | {row.rider_made} of {row.rider_clips} |"
        )
    if mapping.earlier:
        lines += [
            "",
            "Clips recorded by an earlier build are not counted: "
            + ", ".join(f"`{clip_id}`" for clip_id in mapping.earlier)
            + ".",
        ]
    lines += ["", "Clips that did not get all three calls stored:", ""]
    lines += [f"- {line}" for line in mapping.failures] or ["- None."]
    return lines


def report_json(
    runs: Sequence[ClipRun],
    *,
    meta: Mapping[str, Any],
    left_out: Sequence[str],
    gnani_attempts: int,
    mapping: MappingEvidence | None = None,
) -> dict[str, Any]:
    return {
        "meta": {**meta, "gnani_calls_attempted": gnani_attempts},
        "left_out": list(left_out),
        "runs": [asdict(run) for run in runs],
        "mapping": asdict(mapping) if mapping is not None else None,
    }
