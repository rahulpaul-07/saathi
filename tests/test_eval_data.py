import io
import tarfile
from pathlib import Path

import pytest

from saathi.evaluation.flores import (
    ARCHIVE_ROOT,
    FloresError,
    extract_devtest,
    load_devtest,
    sample_indices,
    sha256_of,
)
from saathi.evaluation.wavtools import RecordingError, check_recording, resample_to_16k
from saathi.languages import LANGUAGES
from wavs import make_wav


def _archive(tmp_path: Path, lines: int = 1012, skip: str | None = None) -> Path:
    path = tmp_path / "flores.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for info in LANGUAGES.values():
            if info.indictrans_code == skip:
                continue
            body = "\n".join(f"{info.indictrans_code} line {i}" for i in range(lines)).encode()
            member = tarfile.TarInfo(f"{ARCHIVE_ROOT}/devtest/{info.indictrans_code}.devtest")
            member.size = len(body)
            tar.addfile(member, io.BytesIO(body))
        evil = tarfile.TarInfo("../escape.txt")  # must never be written
        evil.size = 1
        tar.addfile(evil, io.BytesIO(b"x"))
    return path


def test_extract_then_load_roundtrip_and_ignores_unrelated_members(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    data = tmp_path / "data"
    extract_devtest(archive, data, expected_sha256=sha256_of(archive))
    assert load_devtest(data, "bn")[3] == "ben_Beng line 3"
    assert not (tmp_path / "escape.txt").exists()


def test_extract_refuses_a_hash_mismatch(tmp_path: Path) -> None:
    with pytest.raises(FloresError, match="SHA256"):
        extract_devtest(_archive(tmp_path), tmp_path / "data", expected_sha256="0" * 64)


def test_extract_reports_a_missing_language(tmp_path: Path) -> None:
    archive = _archive(tmp_path, skip="tam_Taml")
    with pytest.raises(FloresError, match="missing"):
        extract_devtest(archive, tmp_path / "data", expected_sha256="")


def test_load_rejects_a_truncated_file_and_a_missing_one(tmp_path: Path) -> None:
    archive = _archive(tmp_path, lines=10)
    extract_devtest(archive, tmp_path / "data", expected_sha256="")
    with pytest.raises(FloresError, match="expected 1012"):
        load_devtest(tmp_path / "data", "bn")
    with pytest.raises(FloresError, match="fetch_flores"):
        load_devtest(tmp_path / "empty", "bn")


def test_sample_indices_are_even_unique_and_in_range() -> None:
    picked = sample_indices(1012, 50)
    assert len(picked) == len(set(picked)) == 50
    assert picked[0] == 0 and picked[-1] < 1012
    assert picked == sample_indices(1012, 50)
    with pytest.raises(ValueError):
        sample_indices(10, 11)


def test_resample_24k_tts_audio_to_16k_keeps_duration() -> None:
    import wave

    out = resample_to_16k(make_wav(seconds=2.0, rate=24000))
    with wave.open(io.BytesIO(out)) as clip:
        assert clip.getframerate() == 16000
        assert clip.getnframes() == pytest.approx(32000, abs=64)


def test_check_recording_accepts_16k_mono_and_rejects_everything_else() -> None:
    assert check_recording(make_wav(seconds=3.0)) == pytest.approx(3.0)
    with pytest.raises(RecordingError, match="16 kHz"):
        check_recording(make_wav(seconds=3.0, rate=44100))
    with pytest.raises(RecordingError, match="duration"):
        check_recording(make_wav(seconds=0.2))
    with pytest.raises(RecordingError, match="not a PCM WAV"):
        check_recording(b"not a wav")
