import io
import struct
import wave


def make_wav(seconds: float = 1.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def require_speech_audio(audio: bytes) -> None:
    """What the real /stt/v3 does with unusable audio: a 400, not a transcript. Fakes call this so
    a test that sends empty or non-WAV bytes fails the way production would. It parses with the
    stdlib on purpose, independent of the server's own validator it is meant to back up."""
    from saathi.gnani import GnaniError

    try:
        with wave.open(io.BytesIO(audio)) as wav:
            usable = wav.getnframes() > 0 and wav.getframerate() > 0
    except (wave.Error, EOFError):
        usable = False
    if not usable:
        raise GnaniError("speech service error 400", 400)


def make_streaming_wav(pcm: bytes = bytes([1, 0]) * 8000, rate: int = 16000) -> bytes:
    """A WAV as Gnani TTS returns it: both size fields are 0xFFFFFFFF (unknown length)."""
    unknown = struct.pack("<I", 0xFFFFFFFF)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    return b"RIFF" + unknown + b"WAVEfmt " + struct.pack("<I", 16) + fmt + b"data" + unknown + pcm
