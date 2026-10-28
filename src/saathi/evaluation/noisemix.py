"""Mix noise into a speech clip at a target SNR. Offline and deterministic for a given seed.

SNR is speech-active RMS over noise RMS, so pauses do not flatter the speech level. The activity
detector is deliberately simple: 20 ms frames, a frame is active when its RMS is within 20 dB of
the 95th-percentile frame RMS and above an absolute floor of -60 dBFS. Its settings are logged for
every mix and the active fraction is returned with the result. Noise RMS is taken over the whole
clip (noise does not pause when the speaker does).

Noise comes from a local WAV file (a random window of it, chosen by the seed) or from the built-in
pink-noise generator. Neither is resampled: the speech and the noise must both be 16 kHz mono
16-bit, as the evaluation clips are.
"""

import hashlib
import io
import logging
import wave
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger(__name__)

RATE = 16000
FRAME_S = 0.020
ACTIVE_RELATIVE_DB = -20.0  # a frame counts as speech within this of the loud frames
ACTIVE_FLOOR_DBFS = -60.0  # below this nothing is speech, however quiet the clip is
LOUD_PERCENTILE = 95.0
PEAK_CEILING = 0.99  # the mix is scaled as a whole to stay under this; SNR is unchanged
MIN_SPEECH_S = 0.5
SNR_RANGE_DB = (-10.0, 60.0)

_FULL_SCALE = 32768.0

Samples = NDArray[np.float64]


class NoiseMixError(ValueError):
    """The inputs cannot be mixed at a meaningful SNR."""


@dataclass(frozen=True)
class MixResult:
    wav: bytes
    target_snr_db: float
    measured_snr_db: float  # recomputed from the components actually mixed
    speech_rms_dbfs: float  # speech-active RMS before any peak scaling
    active_fraction: float
    noise_offset: int  # first sample of the noise window used
    peak_scale: float  # 1.0 unless the mix had to be scaled down to avoid clipping


def derive_seed(base_seed: int, *parts: str | int) -> int:
    """A stable per-clip seed (Python's hash() is salted per process, so it is not used)."""
    digest = hashlib.sha256(":".join([str(base_seed), *map(str, parts)]).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def read_wav(data: bytes) -> Samples:
    """16 kHz mono 16-bit PCM WAV -> float samples in [-1, 1)."""
    try:
        with wave.open(io.BytesIO(data)) as clip:
            channels, width, rate = clip.getnchannels(), clip.getsampwidth(), clip.getframerate()
            frames = clip.readframes(clip.getnframes())
    except (wave.Error, EOFError) as exc:
        raise NoiseMixError("not a PCM WAV file") from exc
    if (channels, width, rate) != (1, 2, RATE):
        raise NoiseMixError(
            f"need 16 kHz mono 16-bit, got {rate} Hz, {channels} channel(s), {width * 8}-bit"
        )
    return np.frombuffer(frames, dtype="<i2").astype(np.float64) / _FULL_SCALE


def write_wav(samples: Samples) -> bytes:
    pcm = np.clip(np.rint(samples * _FULL_SCALE), -32768, 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(pcm.tobytes())
    return out.getvalue()


def active_mask(speech: Samples) -> Samples:
    """Per-sample boolean mask (as float 0/1) of speech-active frames. See the module docstring."""
    frame = round(RATE * FRAME_S)
    count = len(speech) // frame
    if count == 0:
        raise NoiseMixError("speech clip is shorter than one analysis frame")
    frames = speech[: count * frame].reshape(count, frame)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    loud = float(np.percentile(rms, LOUD_PERCENTILE))
    threshold = max(loud * 10.0 ** (ACTIVE_RELATIVE_DB / 20.0), 10.0 ** (ACTIVE_FLOOR_DBFS / 20.0))
    active = rms >= threshold
    if not active.any():
        raise NoiseMixError("speech clip is silent: no frame is above the activity floor")
    mask = np.zeros(len(speech))
    mask[: count * frame] = np.repeat(active, frame)
    return mask


def _rms(samples: Samples) -> float:
    return float(np.sqrt(np.mean(np.square(samples))))


def active_rms(samples: Samples, mask: Samples) -> float:
    return _rms(samples[mask > 0])


def pink_noise(seconds: float, seed: int) -> Samples:
    """Seeded 1/f noise (power falls 3 dB per octave), a stand-in for traffic and street rumble.

    Not a recording of any real place: it is a controlled, repeatable stressor, and the write-up
    must say so.
    """
    length = round(seconds * RATE)
    if length < 2:
        raise NoiseMixError("noise length must be at least 2 samples")
    rng = np.random.default_rng(seed)
    spectrum = np.fft.rfft(rng.standard_normal(length))
    shaping = np.ones(len(spectrum))
    shaping[1:] = 1.0 / np.sqrt(np.arange(1, len(spectrum)))
    shaping[0] = 0.0  # no DC offset
    noise: Samples = np.fft.irfft(spectrum * shaping, n=length)
    return noise / _rms(noise) * 0.1


def mix_at_snr(speech: Samples, noise: Samples, snr_db: float, seed: int) -> MixResult:
    """Add a seeded window of `noise` to `speech` so that active-speech RMS / noise RMS = snr_db."""
    if not SNR_RANGE_DB[0] <= snr_db <= SNR_RANGE_DB[1]:
        raise NoiseMixError(f"SNR {snr_db} dB is outside {SNR_RANGE_DB[0]} to {SNR_RANGE_DB[1]}")
    if len(speech) < MIN_SPEECH_S * RATE:
        raise NoiseMixError(f"speech clip is shorter than {MIN_SPEECH_S} s")
    if len(noise) < len(speech):
        raise NoiseMixError(
            f"noise is {len(noise) / RATE:.1f} s, shorter than the {len(speech) / RATE:.1f} s clip"
        )
    mask = active_mask(speech)
    speech_rms = active_rms(speech, mask)
    offset = int(np.random.default_rng(seed).integers(0, len(noise) - len(speech) + 1))
    window = noise[offset : offset + len(speech)]
    window = window - np.mean(window)
    window_rms = _rms(window)
    if window_rms < 10.0 ** (ACTIVE_FLOOR_DBFS / 20.0):
        raise NoiseMixError("noise window is silent")
    scaled = window * (speech_rms / window_rms * 10.0 ** (-snr_db / 20.0))
    mixed = speech + scaled
    peak = float(np.max(np.abs(mixed)))
    peak_scale = min(1.0, PEAK_CEILING / peak)
    log.info(
        "noisemix: %.0f ms frames, active >= max(%.0f dB re p%.0f, %.0f dBFS), active %.0f%%, "
        "target %.1f dB, peak scale %.3f",
        FRAME_S * 1000,
        ACTIVE_RELATIVE_DB,
        LOUD_PERCENTILE,
        ACTIVE_FLOOR_DBFS,
        100 * float(mask.mean()),
        snr_db,
        peak_scale,
    )
    measured = 20.0 * np.log10(speech_rms / _rms(scaled))
    return MixResult(
        wav=write_wav(mixed * peak_scale),
        target_snr_db=snr_db,
        measured_snr_db=float(measured),
        speech_rms_dbfs=float(20.0 * np.log10(speech_rms)),
        active_fraction=float(mask.mean()),
        noise_offset=offset,
        peak_scale=peak_scale,
    )
