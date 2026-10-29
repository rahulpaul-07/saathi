"""Public-speech evaluation: Gnani STT character error rate on FLEURS clips, clean and mixed with
the licensed street bed at 20/10/5 dB. Real human read speech (consented volunteers).

Planning, mixing and run_calls are shared with the gold noise study (`noiseeval`); this module
only adds the clip list, the integrity check and the CER summary. The street and clean
conditions are the same as in the fact study; pink noise is not used here.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from saathi.evaluation.fleurs import Clip, FleursError, audio_path, verify_clip
from saathi.evaluation.metrics import bootstrap_mean_ci, cer
from saathi.evaluation.noiseeval import CLEAN, STREET_CONDITIONS, Condition, PlannedCall

LEDGER_LABEL = "speech-stt"
SPEECH_CONDITIONS = (CLEAN, *STREET_CONDITIONS)
BOOTSTRAP_RESAMPLES = 2000


def plan_speech_calls(
    clips: list[Clip], audio_dir: Path, conditions: tuple[Condition, ...] = SPEECH_CONDITIONS
) -> list[PlannedCall]:
    """One STT call per clip and condition, condition-major so clean is complete first."""
    return [
        PlannedCall(clip, condition, audio_path(audio_dir, clip.lang, clip.file_name))
        for condition in conditions
        for clip in clips
    ]


def verify_audio(clips: list[Clip], audio_dir: Path) -> list[str]:
    """Problems found re-hashing the files against the manifest; empty when all match."""
    problems: list[str] = []
    for clip in clips:
        path = audio_path(audio_dir, clip.lang, clip.file_name)
        if not path.is_file():
            problems.append(f"{clip.clip_id}: audio file is missing (run scripts/fetch_fleurs.py)")
            continue
        try:
            verify_clip(clip, path.read_bytes())
        except FleursError as exc:
            problems.append(str(exc))
    return problems


@dataclass(frozen=True)
class CerCell:
    n: int
    mean: float | None
    low: float | None
    high: float | None


@dataclass(frozen=True)
class CerRow:
    lang: str  # "all" is the pooled row
    cells: dict[str, CerCell]  # by condition name
    delta_vs_clean: dict[str, CerCell]  # paired mean CER increase over clean


def _cell(values: list[float], seed: int) -> CerCell:
    if not values:
        return CerCell(0, None, None, None)
    mean, low, high = bootstrap_mean_ci(values, resamples=BOOTSTRAP_RESAMPLES, seed=seed)
    return CerCell(len(values), mean, low, high)


def summarize_cer(
    clips: list[Clip],
    results: dict[str, dict[str, Any]],
    conditions: tuple[Condition, ...],
    seed: int,
) -> list[CerRow]:
    """Mean CER per language and pooled, with bootstrap CIs over clips.

    Only clips with a result in every condition are used, so conditions compare like with like;
    the delta against clean is paired per clip.
    """
    usable = [c for c in clips if all(f"{c.id}|{k.name}" in results for k in conditions)]
    scores = {
        c.id: {k.name: cer(results[f"{c.id}|{k.name}"]["transcript"], c.raw) for k in conditions}
        for c in usable
    }
    clean = conditions[0].name
    langs = sorted({c.lang for c in usable})
    groups = [(lang, [c for c in usable if c.lang == lang]) for lang in langs]
    groups.append(("all", usable))
    rows = []
    for lang, members in groups:
        cells = {k.name: _cell([scores[c.id][k.name] for c in members], seed) for k in conditions}
        deltas = {
            k.name: _cell([scores[c.id][k.name] - scores[c.id][clean] for c in members], seed)
            for k in conditions[1:]
        }
        rows.append(CerRow(lang, cells, deltas))
    return rows


def format_cer(label: str, rows: list[CerRow], conditions: tuple[Condition, ...]) -> str:
    def cell(c: CerCell) -> str:
        if c.mean is None or c.low is None or c.high is None:
            return "n/a"
        return f"{c.mean:.3f} [{c.low:.3f}, {c.high:.3f}]"

    names = [k.name for k in conditions]
    lines = [
        f"{label}: mean CER (95% bootstrap CI over clips; lower is better)",
        "| language | n | " + " | ".join(names) + " |",
        "|---|---|" + "---|" * len(names),
    ]
    for row in rows:
        cells = " | ".join(cell(row.cells[k]) for k in names)
        lines.append(f"| {row.lang} | {row.cells[names[0]].n} | {cells} |")
    lines.append("")
    lines.append("Paired CER increase over clean (pooled):")
    pooled = rows[-1]
    for name in names[1:]:
        lines.append(f"- {name}: {cell(pooled.delta_vs_clean[name])}")
    return "\n".join(lines)


def rows_as_dict(rows: list[CerRow]) -> list[dict[str, Any]]:
    return [asdict(r) for r in rows]
