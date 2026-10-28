import io
import logging
import wave

import httpx
import numpy as np
import pytest
import respx
from pydantic import SecretStr

from saathi.audio import AudioError
from saathi.config import Settings
from saathi.gnani import TTS_PATH, GnaniClient
from saathi.loudness import (
    PEAK_CEILING_DBFS,
    TARGET_RMS_DBFS,
    normalize_or_passthrough,
    normalize_wav,
)
from wavs import make_streaming_wav

RATE = 24000


def pcm_wav(samples: np.ndarray, channels: int = 1, width: int = 2, rate: int = RATE) -> bytes:
    """Build a WAV from int16 samples (or raw bytes sized for another width)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    return buf.getvalue()


def tone(amplitude: float, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    return np.rint(amplitude * 32767 * np.sin(2 * np.pi * 220 * t)).astype("<i2")


def decode(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data)) as wav:
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64)


def rms_dbfs(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(x**2)) / 32768))


def peak_dbfs(x: np.ndarray) -> float:
    return float(20 * np.log10(np.max(np.abs(x)) / 32768))


def test_quiet_clip_is_raised_to_target_rms() -> None:
    out = decode(normalize_wav(pcm_wav(tone(0.02))))
    assert rms_dbfs(out) == pytest.approx(TARGET_RMS_DBFS, abs=0.3)


def test_loud_clip_is_brought_down_to_target_rms() -> None:
    out = decode(normalize_wav(pcm_wav(tone(0.5))))
    assert rms_dbfs(out) == pytest.approx(TARGET_RMS_DBFS, abs=0.3)


def test_peaky_speech_like_clip_never_exceeds_ceiling() -> None:
    # Quiet bed with rare loud spikes: levelling to the RMS target would push spikes past 0 dBFS.
    rng = np.random.default_rng(0)
    quiet = rng.normal(0, 800, RATE).astype("<i2")
    quiet[[5000, 12000, 20000]] = 30000
    out = decode(normalize_wav(pcm_wav(quiet)))
    assert peak_dbfs(out) <= PEAK_CEILING_DBFS + 0.01
    assert rms_dbfs(out) > rms_dbfs(quiet.astype(np.float64))  # still louder than the input


def test_already_clipping_input_stays_under_ceiling() -> None:
    clipped = np.clip(tone(2.0), -32768, 32767).astype("<i2")
    out = decode(normalize_wav(pcm_wav(clipped)))
    assert peak_dbfs(out) <= PEAK_CEILING_DBFS + 0.01


def test_gain_is_capped_so_hiss_is_not_boosted_forever() -> None:
    faint = tone(0.0005)  # about -66 dBFS peak, above the silence floor
    out = decode(normalize_wav(pcm_wav(faint)))
    assert rms_dbfs(out) - rms_dbfs(faint.astype(np.float64)) <= 30.5


def test_digital_silence_is_returned_unchanged() -> None:
    silent = pcm_wav(np.zeros(RATE, dtype="<i2"))
    assert normalize_wav(silent) == silent


def test_stereo_is_levelled_together_and_stays_stereo() -> None:
    left = tone(0.05)
    stereo = np.column_stack([left, left // 2]).reshape(-1)
    data = normalize_wav(pcm_wav(stereo, channels=2))
    with wave.open(io.BytesIO(data)) as wav:
        assert wav.getnchannels() == 2
        assert wav.getnframes() == len(left)
    assert peak_dbfs(decode(data)) <= PEAK_CEILING_DBFS + 0.01


def test_length_and_rate_are_preserved() -> None:
    out = normalize_wav(pcm_wav(tone(0.1, 0.37)))
    with wave.open(io.BytesIO(out)) as wav:
        assert wav.getframerate() == RATE
        assert wav.getnframes() == int(RATE * 0.37)


def test_non_16bit_audio_is_rejected() -> None:
    with pytest.raises(AudioError, match="16-bit"):
        normalize_wav(pcm_wav(np.zeros(100, dtype="<i4"), width=4))


def test_malformed_wav_is_rejected() -> None:
    with pytest.raises(AudioError):
        normalize_wav(b"not a wav at all")


def test_header_only_wav_is_rejected() -> None:
    with pytest.raises(AudioError, match="no audio"):
        normalize_wav(pcm_wav(np.zeros(0, dtype="<i2")))


def test_passthrough_returns_original_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    junk = b"RIFFxxxxWAVEjunk"
    with caplog.at_level(logging.WARNING, logger="saathi.loudness"):
        assert normalize_or_passthrough(junk) == junk
    assert "skipped" in caplog.text


@respx.mock
async def test_gnani_synthesize_returns_normalized_audio() -> None:
    quiet = tone(0.02).tobytes()
    respx.post(f"https://api.test{TTS_PATH}").mock(
        return_value=httpx.Response(200, content=make_streaming_wav(quiet, rate=RATE))
    )
    client = GnaniClient(Settings(gnani_api_key=SecretStr("k"), gnani_base_url="https://api.test"))
    out = decode(await client.synthesize("hi", "kn-IN", "Saanvi"))
    assert rms_dbfs(out) == pytest.approx(TARGET_RMS_DBFS, abs=0.3)
