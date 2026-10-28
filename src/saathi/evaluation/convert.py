"""Convert phone voice-recorder files to the 16 kHz mono 16-bit PCM WAV the evaluation needs.

ffmpeg does the decoding and resampling. It is run with an argument list (never a shell), the
output is written to a temporary file next to the target and only moved into place once it passes
`check_recording`, so a failed conversion never leaves a half-written or clobbered file.
"""

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from saathi.evaluation.wavtools import TARGET_RATE, RecordingError, check_recording

log = logging.getLogger(__name__)

FFMPEG = "ffmpeg"
TIMEOUT_S = 300
STREET_MIN_SECONDS = 30.0
AUDIO_SUFFIXES = frozenset(
    {".m4a", ".mp3", ".3gp", ".wav", ".aac", ".opus", ".ogg", ".amr", ".flac", ".wma", ".mp4"}
)

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class ConvertError(Exception):
    """One file could not be converted; the message is safe to show to the author."""


@dataclass(frozen=True)
class BatchResult:
    converted: dict[str, float]  # output name -> seconds
    failed: dict[str, str]  # input name -> reason


def _ffmpeg_command(src: Path, tmp: Path) -> list[str]:
    # `-i` takes the next argument as a path, so a file name starting with "-" is not an option.
    return [
        FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-vn", "-ac", "1", "-ar", str(TARGET_RATE), "-c:a", "pcm_s16le",
        "-f", "wav", str(tmp),
    ]  # fmt: skip


def convert_file(
    src: Path, dst: Path, *, force: bool = False, street: bool = False, run: Runner = subprocess.run
) -> float:
    """Convert `src` to `dst`; returns the duration in seconds. Street beds need >= 30 s, no cap."""
    if not src.is_file():
        raise ConvertError(f"input not found: {src}")
    if dst.suffix.lower() != ".wav":
        raise ConvertError(f"output must end in .wav: {dst}")
    if dst.exists() and dst.resolve() == src.resolve():
        raise ConvertError(f"output is the input file: {dst}")
    if dst.exists() and not force:
        raise ConvertError(f"{dst} exists; pass --force to overwrite")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.stem}.converting.wav")
    try:
        _run_ffmpeg(src, tmp, run)
        try:
            data = tmp.read_bytes()
            seconds = (
                check_recording(data, STREET_MIN_SECONDS, None) if street else check_recording(data)
            )
        except RecordingError as exc:
            raise ConvertError(f"{src.name}: converted file is not usable: {exc}") from exc
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    return seconds


def _run_ffmpeg(src: Path, tmp: Path, run: Runner) -> None:
    try:
        done = run(
            _ffmpeg_command(src, tmp),
            capture_output=True, text=True, timeout=TIMEOUT_S, check=False, shell=False,
        )  # fmt: skip
    except FileNotFoundError as exc:
        raise ConvertError("ffmpeg was not found on PATH; install it first") from exc
    except subprocess.TimeoutExpired as exc:
        raise ConvertError(f"{src.name}: ffmpeg timed out after {TIMEOUT_S} s") from exc
    if done.returncode != 0:
        detail = (done.stderr or "").strip().splitlines()
        log.warning("ffmpeg failed for %s: %s", src.name, detail[-3:])
        reason = detail[-1] if detail else f"exit code {done.returncode}"
        raise ConvertError(f"{src.name}: ffmpeg could not read it ({reason})")
    if not tmp.is_file():
        raise ConvertError(f"{src.name}: ffmpeg produced no output")


def convert_batch(
    indir: Path, outdir: Path, *, force: bool = False, run: Runner = subprocess.run
) -> BatchResult:
    """Convert each audio file in `indir` to `outdir/<stem>.wav`; a bad file does not stop more."""
    if not indir.is_dir():
        raise ConvertError(f"input folder not found: {indir}")
    sources = sorted(
        p for p in indir.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES
    )
    stems = [p.stem for p in sources]
    clashes = sorted({s for s in stems if stems.count(s) > 1})
    if clashes:
        raise ConvertError(f"several input files share a name stem: {clashes}")
    converted: dict[str, float] = {}
    failed: dict[str, str] = {}
    for src in sources:
        target = outdir / f"{src.stem}.wav"
        try:
            converted[target.name] = convert_file(src, target, force=force, run=run)
        except ConvertError as exc:
            failed[src.name] = str(exc)
    return BatchResult(converted, failed)
