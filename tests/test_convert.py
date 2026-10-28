import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from saathi.evaluation.convert import ConvertError, convert_batch, convert_file
from wavs import make_wav

ROOT = Path(__file__).resolve().parent.parent


class FakeFfmpeg:
    """Stands in for subprocess.run: records the command and writes a WAV where ffmpeg would."""

    def __init__(
        self, seconds: float = 5.0, rate: int = 16000, code: int = 0, stderr: str = ""
    ) -> None:
        self.seconds, self.rate, self.code, self.stderr = seconds, rate, code, stderr
        self.commands: list[list[str]] = []
        self.kwargs: list[dict[str, Any]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> "subprocess.CompletedProcess[str]":
        self.commands.append(command)
        self.kwargs.append(kwargs)
        if self.code == 0:
            Path(command[-1]).write_bytes(make_wav(self.seconds, rate=self.rate))
        return subprocess.CompletedProcess(command, self.code, "", self.stderr)


def _input(tmp_path: Path, name: str = "g01.m4a") -> Path:
    path = tmp_path / name
    path.write_bytes(b"not really audio")
    return path


def test_converts_with_an_argument_list_and_the_target_format(tmp_path: Path) -> None:
    fake = FakeFfmpeg(seconds=5.0)
    src, dst = _input(tmp_path), tmp_path / "out" / "g01.wav"
    assert convert_file(src, dst, run=fake) == pytest.approx(5.0)
    command, kwargs = fake.commands[0], fake.kwargs[0]
    assert command[0] == "ffmpeg" and isinstance(command, list)
    assert command[command.index("-i") + 1] == str(src)
    assert command[command.index("-ar") + 1] == "16000"
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-c:a") + 1] == "pcm_s16le"
    assert kwargs["shell"] is False
    assert dst.read_bytes() == make_wav(5.0)
    assert [p.name for p in dst.parent.iterdir()] == ["g01.wav"]  # no temp file left behind


def test_missing_input_never_calls_ffmpeg(tmp_path: Path) -> None:
    fake = FakeFfmpeg()
    with pytest.raises(ConvertError, match="input not found"):
        convert_file(tmp_path / "nope.m4a", tmp_path / "x.wav", run=fake)
    assert fake.commands == []


def test_refuses_to_overwrite_without_force_and_allows_it_with_force(tmp_path: Path) -> None:
    src, dst = _input(tmp_path), tmp_path / "g01.wav"
    dst.write_bytes(b"precious")
    fake = FakeFfmpeg()
    with pytest.raises(ConvertError, match="--force"):
        convert_file(src, dst, run=fake)
    assert dst.read_bytes() == b"precious" and fake.commands == []
    convert_file(src, dst, force=True, run=fake)
    assert dst.read_bytes() == make_wav(5.0)


def test_never_overwrites_the_input_even_with_force(tmp_path: Path) -> None:
    src = _input(tmp_path, "g01.wav")
    with pytest.raises(ConvertError, match="is the input"):
        convert_file(src, src, force=True, run=FakeFfmpeg())
    assert src.read_bytes() == b"not really audio"


def test_output_must_be_wav(tmp_path: Path) -> None:
    with pytest.raises(ConvertError, match=r"\.wav"):
        convert_file(_input(tmp_path), tmp_path / "g01.mp3", run=FakeFfmpeg())


def test_missing_ffmpeg_is_a_clear_error(tmp_path: Path) -> None:
    def no_ffmpeg(command: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError("ffmpeg")

    with pytest.raises(ConvertError, match="ffmpeg was not found"):
        convert_file(_input(tmp_path), tmp_path / "g01.wav", run=no_ffmpeg)
    assert not (tmp_path / "g01.wav").exists()


def test_ffmpeg_failure_on_bad_input_leaves_nothing_behind(tmp_path: Path) -> None:
    fake = FakeFfmpeg(code=1, stderr="warn\nInvalid data found when processing input")
    with pytest.raises(ConvertError, match="Invalid data found"):
        convert_file(_input(tmp_path), tmp_path / "g01.wav", run=fake)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["g01.m4a"]


def test_ffmpeg_timeout_is_reported(tmp_path: Path) -> None:
    def slow(command: list[str], **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(command, 1)

    with pytest.raises(ConvertError, match="timed out"):
        convert_file(_input(tmp_path), tmp_path / "g01.wav", run=slow)


def test_output_that_fails_the_recording_check_is_not_kept(tmp_path: Path) -> None:
    dst = tmp_path / "g01.wav"
    with pytest.raises(ConvertError, match="not usable"):
        convert_file(_input(tmp_path), dst, run=FakeFfmpeg(seconds=90.0))  # speech max is 60 s
    with pytest.raises(ConvertError, match="not usable"):
        convert_file(_input(tmp_path), dst, run=FakeFfmpeg(seconds=0.2))
    assert not dst.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["g01.m4a"]


def test_street_mode_allows_long_files_and_requires_30_seconds(tmp_path: Path) -> None:
    dst = tmp_path / "noise" / "street.wav"
    assert convert_file(_input(tmp_path), dst, street=True, run=FakeFfmpeg(seconds=90.0)) == 90.0
    with pytest.raises(ConvertError, match="at least 30 s"):
        convert_file(
            _input(tmp_path), tmp_path / "short.wav", street=True, run=FakeFfmpeg(seconds=20.0)
        )


def test_batch_maps_by_stem_skips_non_audio_and_reports_failures(tmp_path: Path) -> None:
    indir, outdir = tmp_path / "in", tmp_path / "out"
    indir.mkdir()
    for name in ("g01.m4a", "g02.mp3", "g03.3gp", "notes.txt"):
        (indir / name).write_bytes(b"x")
    (indir / "nested").mkdir()
    (outdir).mkdir()
    (outdir / "g02.wav").write_bytes(b"keep")  # exists: that file fails, the others go on
    result = convert_batch(indir, outdir, run=FakeFfmpeg())
    assert sorted(result.converted) == ["g01.wav", "g03.wav"]
    assert list(result.failed) == ["g02.mp3"] and "--force" in result.failed["g02.mp3"]
    assert (outdir / "g02.wav").read_bytes() == b"keep"


def test_batch_rejects_duplicate_stems_and_missing_folder(tmp_path: Path) -> None:
    indir = tmp_path / "in"
    indir.mkdir()
    (indir / "g01.m4a").write_bytes(b"x")
    (indir / "g01.mp3").write_bytes(b"x")
    with pytest.raises(ConvertError, match="share a name stem"):
        convert_batch(indir, tmp_path / "out", run=FakeFfmpeg())
    with pytest.raises(ConvertError, match="folder not found"):
        convert_batch(tmp_path / "absent", tmp_path / "out", run=FakeFfmpeg())


def test_cli_reports_a_missing_input_without_needing_ffmpeg(tmp_path: Path) -> None:
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "convert_recording.py"),
         str(tmp_path / "nope.m4a"), str(tmp_path / "x.wav")],
        capture_output=True, text=True, cwd=tmp_path,
    )  # fmt: skip
    assert out.returncode == 1 and "input not found" in out.stderr
    assert "Traceback" not in out.stderr
