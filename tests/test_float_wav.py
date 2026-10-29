import io
import struct

import numpy as np
import pytest

from saathi.evaluation.wavtools import RecordingError, check_recording, float_wav_to_pcm16
from wavs import make_wav


def float_wav(samples: list[float], rate: int = 16_000, tag: int = 3) -> bytes:
    data = np.array(samples, dtype="<f4").tobytes()
    fmt = struct.pack("<HHIIHH", tag, 1, rate, rate * 4, 4, 32)
    fact = b"fact" + struct.pack("<II", 4, len(samples))
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + fact + b"data"
    body += struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_float_wav_becomes_16_bit_pcm_that_passes_the_clip_check() -> None:
    seconds = 2
    samples = [0.5] * (16_000 * seconds)
    out = float_wav_to_pcm16(float_wav(samples))
    assert check_recording(out) == seconds
    assert np.frombuffer(out[44:], dtype="<i2")[0] == round(0.5 * 32767)


def test_out_of_range_samples_are_clipped_not_wrapped() -> None:
    out = float_wav_to_pcm16(float_wav([2.0, -2.0] * 8000))
    values = np.frombuffer(out[44:], dtype="<i2")
    assert values.max() == 32767 and values.min() == -32768


def test_other_formats_are_refused() -> None:
    with pytest.raises(RecordingError):
        float_wav_to_pcm16(make_wav())
    with pytest.raises(RecordingError):
        float_wav_to_pcm16(io.BytesIO(b"not a wav").getvalue())
