"""Noise evaluation: gold-set recordings, clean and mixed with recorded street noise at 20/10/5 dB
SNR (primary) and seeded pink noise at 10 dB (secondary), through Gnani STT, then critical-fact
precision and recall with bootstrap confidence intervals (docs/DESIGN.md 11).

The planning, mixing and scoring here are offline. Only `run_calls` talks to a client, and it is
handed one (the real one is `MeteredGnani`, so every call is counted in the ledger first).
"""

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np

from saathi.evaluation import noisemix
from saathi.evaluation.calls import BudgetExceededError, CallLedger, SlidingWindowLimiter
from saathi.evaluation.factscore import GoldUtterance, score_transcript
from saathi.evaluation.noisemix import Samples
from saathi.evaluation.turns import call_with_retry
from saathi.evaluation.wavtools import RecordingError, check_recording
from saathi.languages import LANGUAGES

log = logging.getLogger(__name__)

LEDGER_LABEL = "noise-stt"
BOOTSTRAP_RESAMPLES = 2000
CONFIDENCE = 0.95


STREET_MIN_SECONDS = 30.0


@dataclass(frozen=True)
class Condition:
    name: str
    snr_db: float | None  # None is the clean recording, sent untouched
    noise: Literal["street", "pink"] | None = None


CLEAN = Condition("clean", None)
# Primary: a recorded street-traffic bed. Secondary: seeded pink noise, a controlled stressor.
STREET_CONDITIONS = (
    Condition("street_20", 20.0, "street"),
    Condition("street_10", 10.0, "street"),
    Condition("street_5", 5.0, "street"),
)
PINK_CONDITIONS = (Condition("pink_10", 10.0, "pink"),)
CONDITIONS = (CLEAN, *STREET_CONDITIONS, *PINK_CONDITIONS)
# Reported as separate tables, each against clean; street and pink are never pooled.
REPORT_SETS = (
    ("street (primary)", (CLEAN, *STREET_CONDITIONS)),
    ("pink (secondary)", (CLEAN, *PINK_CONDITIONS)),
)


class Subject(Protocol):
    """Anything with a stable id and a language: a gold utterance or a public-speech clip."""

    @property
    def id(self) -> str: ...

    @property
    def lang(self) -> str: ...


@dataclass(frozen=True)
class PlannedCall:
    utterance: Subject
    condition: Condition
    path: Path

    @property
    def key(self) -> str:
        return f"{self.utterance.id}|{self.condition.name}"


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, filename: str, language_code: str) -> str: ...


def plan_calls(
    gold: list[GoldUtterance], audio_dir: Path, conditions: tuple[Condition, ...] = CONDITIONS
) -> list[PlannedCall]:
    """One STT call per utterance and condition, condition-major so clean is complete first."""
    return [PlannedCall(u, c, audio_dir / f"{u.id}.wav") for c in conditions for u in gold]


def missing_audio(calls: list[PlannedCall]) -> list[Path]:
    return sorted({c.path for c in calls if not c.path.is_file()})


def check_budget(ledger: CallLedger, calls: int) -> None:
    """Refuse a plan that would pass the hard cap, before anything is sent."""
    if ledger.total + calls > ledger.cap:
        raise BudgetExceededError(
            f"{calls} planned calls + {ledger.total} spent exceeds the cap of {ledger.cap}"
        )


def format_plan(
    calls: list[PlannedCall],
    done: set[str],
    ledger: CallLedger,
    problems: list[str],
    street_note: str = "",
) -> str:
    pending = [c for c in calls if c.key not in done]
    lines = [f"Planned Gnani STT calls ({len(pending)} pending, {len(done)} already in results):"]
    for number, call in enumerate(pending, 1):
        state = "ok" if call.path.is_file() else "MISSING"
        lines.append(
            f"  {number:3} {call.utterance.id} {call.utterance.lang} {call.condition.name:<9} "
            f"{call.path.as_posix()} [{state}]"
        )
    absent = missing_audio(pending)
    after = ledger.total + len(pending)
    per_condition = {c.condition.name: 0 for c in pending}
    for c in pending:
        per_condition[c.condition.name] += 1
    lines.append("By condition: " + ", ".join(f"{n} {k}" for k, n in per_condition.items()))
    if street_note:
        lines.append(street_note)
    lines.append(f"Recordings missing: {len(absent)} of {len({c.path for c in pending})}")
    lines.extend(f"  problem: {p}" for p in problems)
    lines.append(
        f"Ledger: {ledger.total} spent + {len(pending)} planned = {after} of cap {ledger.cap}; "
        f"retry headroom {ledger.cap - after}"
    )
    lines.append("Pacing: at most 3 calls in any 10 s; 429s are retried and counted.")
    return "\n".join(lines)


def _load_street(wav: bytes | None, longest_speech_s: float) -> tuple[Samples | None, str]:
    """The street bed as samples, or None and one problem line saying why it cannot be used."""
    if wav is None:
        return None, "street noise file is missing (record one and convert_recording --street)"
    try:
        seconds = check_recording(wav, STREET_MIN_SECONDS, None)
        samples = noisemix.read_wav(wav)
    except (RecordingError, noisemix.NoiseMixError) as exc:
        return None, f"street noise file: {exc}"
    if seconds < longest_speech_s:
        return None, (
            f"street noise file is {seconds:.1f} s, shorter than the longest utterance "
            f"({longest_speech_s:.1f} s)"
        )
    return samples, ""


@dataclass(frozen=True)
class PreparedClip:
    wav: bytes
    measured_snr_db: float | None
    active_fraction: float | None


def prepare_clips(
    calls: list[PlannedCall], base_seed: int, street_wav: bytes | None
) -> tuple[dict[str, PreparedClip], list[str]]:
    """Read, validate and mix every clip whose recording exists, before any paid call.

    Street clips need `street_wav` (the recorded bed); pink clips use seeded synthetic noise.
    Returns the clips by call key and a list of problems (bad format, mixing refused).
    """
    problems: list[str] = []
    speech: dict[Path, tuple[bytes, Samples]] = {}
    for path in sorted({c.path for c in calls if c.path.is_file()}):
        try:
            data = path.read_bytes()
            check_recording(data)
            speech[path] = (data, noisemix.read_wav(data))
        except (OSError, RecordingError, noisemix.NoiseMixError) as exc:
            problems.append(f"{path.name}: {exc}")
    longest = max((len(s[1]) for s in speech.values()), default=0) / noisemix.RATE
    pink = noisemix.pink_noise(longest + 1.0, noisemix.derive_seed(base_seed, "noise"))
    street, street_problem = _load_street(street_wav, longest)
    if street_problem and any(c.condition.noise == "street" for c in calls):
        problems.append(street_problem)

    clips: dict[str, PreparedClip] = {}
    for call in calls:
        if call.path not in speech:
            continue
        data, samples = speech[call.path]
        if call.condition.snr_db is None:
            clips[call.key] = PreparedClip(data, None, None)
            continue
        noise = street if call.condition.noise == "street" else pink
        if noise is None:
            continue  # the street problem is already listed once
        seed = noisemix.derive_seed(base_seed, call.utterance.id, call.condition.name)
        try:
            mix = noisemix.mix_at_snr(samples, noise, call.condition.snr_db, seed)
        except noisemix.NoiseMixError as exc:
            problems.append(f"{call.key}: {exc}")
            continue
        clips[call.key] = PreparedClip(mix.wav, mix.measured_snr_db, mix.active_fraction)
    return clips, problems


async def run_calls(
    calls: list[PlannedCall],
    clips: dict[str, PreparedClip],
    gnani: Transcriber,
    limiter: SlidingWindowLimiter,
    ledger: CallLedger,
    results: dict[str, dict[str, Any]],
    save: Callable[[dict[str, dict[str, Any]]], None],
) -> None:
    """Send each pending clip once, saving after every call so a stop never loses paid results.

    The budget is checked for the whole run first; the metered client then counts every HTTP
    call, retries included, and raises if the cap would be passed anyway.
    """
    pending = [c for c in calls if c.key not in results]
    check_budget(ledger, len(pending))
    unready = [c.key for c in pending if c.key not in clips]
    if unready:
        raise RecordingError(f"{len(unready)} clips are not ready, nothing sent: {unready[:3]}")
    for call in pending:
        clip = clips[call.key]
        language = LANGUAGES[call.utterance.lang].gnani_code
        transcript, retries = await call_with_retry(
            partial(gnani.transcribe, clip.wav, "turn.wav", language), limiter
        )
        results[call.key] = {
            "id": call.utterance.id,
            "condition": call.condition.name,
            "transcript": transcript.strip(),
            "retries": retries,
            "measured_snr_db": clip.measured_snr_db,
            "active_fraction": clip.active_fraction,
        }
        save(results)


def load_results(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data["rows"])


def save_results(path: Path, meta: dict[str, Any], rows: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "rows": rows}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


@dataclass(frozen=True)
class Interval:
    point: float | None
    low: float | None
    high: float | None


@dataclass(frozen=True)
class ConditionSummary:
    condition: str
    n: int
    precision: Interval
    recall: Interval
    all_right: Interval
    recall_drop_vs_clean: Interval | None  # paired: same resampled utterances as clean


def _ratio(num: np.ndarray[Any, Any], den: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    out = np.full(num.shape, np.nan)
    np.divide(num, den, out=out, where=den > 0)
    return out


def _interval(point: float, samples: np.ndarray[Any, Any]) -> Interval:
    valid = samples[~np.isnan(samples)]
    if np.isnan(point) or len(valid) == 0:
        return Interval(None, None, None)
    tail = (1 - CONFIDENCE) / 2 * 100
    low, high = np.percentile(valid, [tail, 100 - tail])
    return Interval(float(point), float(low), float(high))


def summarize(
    gold: list[GoldUtterance],
    results: dict[str, dict[str, Any]],
    conditions: tuple[Condition, ...],
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> list[ConditionSummary]:
    """Precision, recall and all-facts-right share per condition, bootstrapped over utterances.

    Only utterances with a result in every listed condition are used, so conditions compare like
    with like. One set of resampled indices is shared by all conditions (paired).
    """
    usable = [u for u in gold if all(f"{u.id}|{c.name}" in results for c in conditions)]
    if not usable:
        return []
    counts: dict[str, np.ndarray[Any, Any]] = {}
    for condition in conditions:
        rows = []
        for u in usable:
            report = score_transcript(u, results[f"{u.id}|{condition.name}"]["transcript"])
            total = report.overall
            rows.append((total.tp, total.fp, total.fn, report.all_correct))
        counts[condition.name] = np.array(rows, dtype=float)
    rng = np.random.default_rng(seed)
    index = rng.integers(0, len(usable), size=(resamples, len(usable)))

    def metrics(
        table: np.ndarray[Any, Any], rows: np.ndarray[Any, Any] | None
    ) -> np.ndarray[Any, Any]:
        part = table if rows is None else table[rows]
        total = part.sum(axis=-2)
        return np.stack(
            [
                _ratio(total[..., 0], total[..., 0] + total[..., 1]),
                _ratio(total[..., 0], total[..., 0] + total[..., 2]),
                total[..., 3] / part.shape[-2],
            ]
        )

    clean_name = conditions[0].name
    clean_point = metrics(counts[clean_name], None)
    clean_boot = metrics(counts[clean_name], index)
    summaries = []
    for condition in conditions:
        table = counts[condition.name]
        point, boot = metrics(table, None), metrics(table, index)
        drop = None
        if condition.name != clean_name:
            drop = _interval(clean_point[1] - point[1], clean_boot[1] - boot[1])
        summaries.append(
            ConditionSummary(
                condition.name,
                len(usable),
                _interval(float(point[0]), boot[0]),
                _interval(float(point[1]), boot[1]),
                _interval(float(point[2]), boot[2]),
                drop,
            )
        )
    return summaries


def format_summary(label: str, summaries: list[ConditionSummary]) -> str:
    def cell(i: Interval) -> str:
        if i.point is None or i.low is None or i.high is None:
            return "n/a"
        return f"{i.point:.2f} [{i.low:.2f}, {i.high:.2f}]"

    lines = [
        f"{label}: precision / recall / all-facts-right (95% bootstrap CI over utterances)",
        "| condition | n | precision | recall | all facts right | recall drop vs clean |",
        "|---|---|---|---|---|---|",
    ]
    for s in summaries:
        drop = cell(s.recall_drop_vs_clean) if s.recall_drop_vs_clean else "-"
        lines.append(
            f"| {s.condition} | {s.n} | {cell(s.precision)} | {cell(s.recall)} "
            f"| {cell(s.all_right)} | {drop} |"
        )
    return "\n".join(lines)


def summaries_as_dict(summaries: list[ConditionSummary]) -> list[dict[str, Any]]:
    return [asdict(s) for s in summaries]
