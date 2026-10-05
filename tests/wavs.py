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


def make_streaming_wav(pcm: bytes = bytes([1, 0]) * 8000, rate: int = 16000) -> bytes:
    """A WAV as Gnani TTS returns it: both size fields are 0xFFFFFFFF (unknown length)."""
    unknown = struct.pack("<I", 0xFFFFFFFF)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    return b"RIFF" + unknown + b"WAVEfmt " + struct.pack("<I", 16) + fmt + b"data" + unknown + pcm
