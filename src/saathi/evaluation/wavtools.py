"""WAV helpers: Gnani TTS audio down to what the browser would upload, and recording checks."""

import io
import struct
import warnings
import wave

import numpy as np

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


def float_wav_to_pcm16(wav_bytes: bytes) -> bytes:
    """Mono 32-bit float WAV (FLEURS ships this) -> 16-bit PCM at the same rate.

    The stdlib `wave` module cannot read float WAVs, so the RIFF chunks are walked by hand.
    """
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise RecordingError("not a RIFF/WAVE file")
    fmt: tuple[int, int, int, int] | None = None
    data: bytes | None = None
    position = 12
    while position + 8 <= len(wav_bytes):
        chunk_id = wav_bytes[position : position + 4]
        size = int.from_bytes(wav_bytes[position + 4 : position + 8], "little")
        body = wav_bytes[position + 8 : position + 8 + size]
        if chunk_id == b"fmt " and len(body) >= 16:
            tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            fmt = (tag, channels, rate, bits)
        elif chunk_id == b"data":
            data = body
        position += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise RecordingError("WAV file has no fmt or data chunk")
    tag, channels, rate, bits = fmt
    if (tag, channels, bits) != (3, 1, 32):
        raise RecordingError(f"expected mono 32-bit float audio, got tag {tag}, {bits}-bit")
    samples = np.frombuffer(data[: len(data) // 4 * 4], dtype="<f4")
    pcm = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(pcm.tobytes())
    return out.getvalue()


def check_recording(
    wav_bytes: bytes, min_seconds: float = MIN_SECONDS, max_seconds: float | None = MAX_SECONDS
) -> float:
    """Validate a recorded clip before any paid call; returns its duration in seconds.

    Speech clips use the default 1-60 s window; a noise bed passes its own bounds (no maximum).
    """
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
    if seconds < min_seconds or (max_seconds is not None and seconds > max_seconds):
        window = (
            f"{min_seconds:.0f}-{max_seconds:.0f} s"
            if max_seconds is not None
            else f"at least {min_seconds:.0f} s"
        )
        raise RecordingError(f"duration {seconds:.1f} s is outside {window}")
    return seconds
