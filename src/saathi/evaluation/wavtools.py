"""WAV helpers: Gnani TTS audio down to what the browser would upload, and recording checks."""

import io
import warnings
import wave

with warnings.catch_warnings():
    # audioop is removed in 3.13; the project pins Python 3.12 and this is dev tooling.
    warnings.simplefilter("ignore", DeprecationWarning)
    import audioop

TARGET_RATE = 16000
MIN_SECONDS = 1.0
MAX_SECONDS = 60.0


class RecordingError(ValueError):
    """A WAV file is not usable as an evaluation clip."""


def resample_to_16k(wav_bytes: bytes) -> bytes:
    """Mono 16-bit WAV at any rate -> 16 kHz, like the browser's upload."""
    with wave.open(io.BytesIO(wav_bytes)) as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise RecordingError("expected mono 16-bit audio")
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
    if rate != TARGET_RATE:
        frames, _ = audioop.ratecv(frames, 2, 1, rate, TARGET_RATE, None)
    out = io.BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(TARGET_RATE)
        target.writeframes(frames)
    return out.getvalue()


def check_recording(wav_bytes: bytes) -> float:
    """Validate a recorded clip before any paid call; returns its duration in seconds."""
    try:
        with wave.open(io.BytesIO(wav_bytes)) as clip:
            channels, width, rate = clip.getnchannels(), clip.getsampwidth(), clip.getframerate()
            frames = clip.getnframes()
    except (wave.Error, EOFError) as exc:
        raise RecordingError("not a PCM WAV file") from exc
    if (channels, width, rate) != (1, 2, TARGET_RATE):
        raise RecordingError(
            f"need 16 kHz mono 16-bit, got {rate} Hz, {channels} channel(s), {width * 8}-bit"
        )
    seconds: float = frames / rate
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise RecordingError(
            f"duration {seconds:.1f} s is outside {MIN_SECONDS:.0f}-{MAX_SECONDS:.0f} s"
        )
    return seconds
