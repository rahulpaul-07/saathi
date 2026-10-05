import pytest

from saathi.audio import AudioError, finalize_streaming_wav, wav_duration_s
from wavs import make_streaming_wav, make_wav


def test_returns_duration_from_header() -> None:
    assert wav_duration_s(make_wav(2.0)) == pytest.approx(2.0)


def test_rejects_zero_frames() -> None:
    with pytest.raises(AudioError, match="empty"):
        wav_duration_s(make_wav(0))


def test_rejects_truncated_header() -> None:
    with pytest.raises(AudioError):
        wav_duration_s(make_wav()[:10])


def test_finalize_streaming_wav_writes_real_sizes() -> None:
    fixed = finalize_streaming_wav(make_streaming_wav())
    assert wav_duration_s(fixed) == pytest.approx(0.5)


def test_finalize_leaves_a_correct_wav_unchanged() -> None:
    good = make_wav(1.0)
    assert finalize_streaming_wav(good) == good


@pytest.mark.parametrize("junk", [b"", b"not audio at all", b"RIFF\x00\x00\x00\x00WAVE"])
def test_finalize_rejects_non_wav(junk: bytes) -> None:
    with pytest.raises(AudioError):
        finalize_streaming_wav(junk)
