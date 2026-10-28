"""Loudness normalization for TTS audio, so a rider outdoors hears every reply at a similar level.

RMS is the loudness proxy (speech is not tonal, so crest factor is similar between voices); a
look-around peak limiter then guarantees the result never clips. Only 16-bit PCM is handled, which
is what the Gnani client requests.
"""

import io
import logging
import wave

import numpy as np
from numpy.typing import NDArray

from saathi.audio import AudioError

log = logging.getLogger(__name__)

TARGET_RMS_DBFS = -18.0  # loud enough for a phone speaker outdoors, with headroom for peaks
PEAK_CEILING_DBFS = -1.0  # leaves room for the DAC and any lossy re-encode on the device
MAX_GAIN_DB = 30.0  # a near-silent clip is not worth amplifying into hiss
SILENCE_RMS_DBFS = -70.0  # below this there is no speech to level; the clip is returned unchanged
LIMITER_WINDOW_S = 0.005  # gain reduction ramps over about this long, which avoids clicks

_FULL_SCALE = 32768.0


def _db(level_db: float) -> float:
    return float(10.0 ** (level_db / 20.0))


def _limiter_gain(
    frame_peak: NDArray[np.float32], ceiling: float, window: int
) -> NDArray[np.float32]:
    """Per-frame gain <= 1 that keeps every frame at or below the ceiling.

    The required gain is min-filtered over +/- one window and then box-averaged over one window, so
    each smoothed value is built only from required gains at or below the one at that frame: the
    ceiling holds exactly while the gain changes gradually.
    """
    required = np.minimum(1.0, ceiling / np.maximum(frame_peak, 1e-9)).astype(np.float32)
    if window <= 1 or required.min() >= 1.0:
        return required
    pad = window - 1
    padded = np.pad(required, pad, constant_values=1.0)
    lows = np.lib.stride_tricks.sliding_window_view(padded, 2 * pad + 1).min(axis=1)
    kernel = np.full(window, 1.0 / window, dtype=np.float32)
    padded_lows = np.pad(lows, window // 2, mode="edge")
    return np.convolve(padded_lows, kernel, mode="valid")[: len(required)].astype(np.float32)


def normalize_wav(data: bytes) -> bytes:
    """Return the WAV levelled to the target RMS and limited to the peak ceiling.

    Raises AudioError for anything that is not a readable 16-bit PCM WAV. A clip that is digital
    silence is returned unchanged.
    """
    try:
        with wave.open(io.BytesIO(data)) as source:
            channels, width = source.getnchannels(), source.getsampwidth()
            rate = source.getframerate()
            frames = source.readframes(source.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioError("audio must be a PCM WAV file") from exc
    if width != 2:
        raise AudioError(f"only 16-bit audio can be normalized, got {width * 8}-bit")
    if channels < 1 or rate < 1:
        raise AudioError("WAV header is invalid")
    usable = len(frames) - len(frames) % (2 * channels)
    if usable == 0:
        raise AudioError("WAV has no audio data")

    samples = np.frombuffer(frames[:usable], dtype="<i2").astype(np.float32) / _FULL_SCALE
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float32))))
    if rms < _db(SILENCE_RMS_DBFS):
        log.info("loudness: clip is silent, left unchanged")
        return data

    gain = min(_db(TARGET_RMS_DBFS) / rms, _db(MAX_GAIN_DB))
    leveled = (samples * gain).reshape(-1, channels)
    window = max(1, round(rate * LIMITER_WINDOW_S))
    limiter = _limiter_gain(np.abs(leveled).max(axis=1), _db(PEAK_CEILING_DBFS), window)
    out = np.rint(leveled * limiter[:, None] * _FULL_SCALE)
    pcm = np.clip(out, -32768, 32767).astype("<i2")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(pcm.tobytes())
    return buffer.getvalue()


def normalize_or_passthrough(data: bytes) -> bytes:
    """Normalize, or return the audio untouched if it cannot be.

    Quiet audio is better than no audio, so a clip the normalizer rejects is still played. The
    reason goes to the log (never the audio itself).
    """
    try:
        return normalize_wav(data)
    except AudioError as exc:
        log.warning("loudness normalization skipped: %s", exc)
        return data
