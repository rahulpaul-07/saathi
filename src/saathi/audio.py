"""Validation of uploaded audio, done before any paid Gnani call is made."""

import io
import struct
import wave

MAX_AUDIO_BYTES = 2_500_000  # 60 s of 16 kHz mono 16-bit PCM is 1.92 MB
MAX_AUDIO_SECONDS = 60.0  # Prisma's documented per-request limit
# Our own sanity limits, not Gnani's documented ones: a clip shorter than this is a mis-tap and
# a rate outside this range is not speech from any browser, so neither is worth a paid call.
MIN_AUDIO_SECONDS = 0.3
MIN_SAMPLE_RATE_HZ = 8_000
MAX_SAMPLE_RATE_HZ = 48_000


class AudioError(ValueError):
    """The upload is not a WAV file the pipeline can accept."""


class AudioTooLargeError(AudioError):
    """The upload exceeds the byte cap."""


def wav_duration_s(data: bytes) -> float:
    """Return the duration of a PCM WAV, or raise AudioError.

    Only the header is trusted for the duration, so this also guards the claimed length against
    the Prisma limit rather than relying on the browser to have trimmed it.
    """
    if len(data) > MAX_AUDIO_BYTES:
        raise AudioTooLargeError("audio file too large")
    try:
        with wave.open(io.BytesIO(data)) as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
    except (wave.Error, EOFError) as exc:
        raise AudioError("audio must be a PCM WAV file") from exc
    if frames == 0 or rate == 0:
        raise AudioError("audio is empty")
    if not MIN_SAMPLE_RATE_HZ <= rate <= MAX_SAMPLE_RATE_HZ:
        raise AudioError(f"sample rate {rate} Hz is outside the accepted range")
    duration: float = frames / rate
    if duration < MIN_AUDIO_SECONDS:
        raise AudioError(f"audio shorter than {MIN_AUDIO_SECONDS} seconds")
    if duration > MAX_AUDIO_SECONDS:
        raise AudioError(f"audio longer than {MAX_AUDIO_SECONDS:.0f} seconds")
    return duration


def finalize_streaming_wav(data: bytes) -> bytes:
    """Give a streamed WAV real size fields.

    Gnani TTS sends 0xFFFFFFFF for both the RIFF and `data` sizes because it streams. Python's
    `wave` and some browsers (notably iOS Safari) take those literally, so the sizes are rewritten
    from the bytes actually received. A WAV whose sizes are already valid is returned unchanged.
    """
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AudioError("not a WAV file")
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        (size,) = struct.unpack("<I", data[pos + 4 : pos + 8])
        body = pos + 8
        if chunk_id == b"data":
            actual = len(data) - body
            if actual <= 0:
                raise AudioError("WAV has no audio data")
            if size <= actual:
                return data
            fixed = bytearray(data)
            fixed[4:8] = struct.pack("<I", len(data) - 8)
            fixed[pos + 4 : pos + 8] = struct.pack("<I", actual)
            return bytes(fixed)
        pos = body + size + (size & 1)  # chunks are padded to an even length
    raise AudioError("WAV has no data chunk")
