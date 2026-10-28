import numpy as np
import pytest

from saathi.evaluation import noisemix as nm
from saathi.evaluation.noisemix import NoiseMixError, mix_at_snr, pink_noise
from wavs import make_wav


def _speechlike(seconds: float = 4.0, seed: int = 1) -> nm.Samples:
    """Loud bursts separated by near-silence, so active-RMS and whole-clip RMS clearly differ."""
    rng = np.random.default_rng(seed)
    n = round(seconds * nm.RATE)
    t = np.arange(n) / nm.RATE
    envelope = (np.sin(2 * np.pi * 1.5 * t) > 0).astype(float)  # on/off about every 0.33 s
    voice = 0.3 * np.sin(2 * np.pi * 220 * t) * envelope
    out: nm.Samples = voice + 0.0005 * rng.standard_normal(n)
    return out


def _wav_samples(wav: bytes) -> nm.Samples:
    return nm.read_wav(wav)


@pytest.mark.parametrize("snr", [20.0, 10.0, 5.0])
def test_measured_snr_matches_target_on_the_output_file(snr: float) -> None:
    speech = _speechlike()
    noise = pink_noise(10.0, seed=3)
    result = mix_at_snr(speech, noise, snr, seed=7)

    # Independent check from the written WAV: mixture minus the (quantized) clean speech scaled by
    # the same peak factor is the noise that was actually added.
    mixed = _wav_samples(result.wav)
    clean = _wav_samples(nm.write_wav(speech * result.peak_scale))
    added = mixed - clean
    speech_active = nm.active_rms(clean, nm.active_mask(speech))
    measured = 20 * np.log10(speech_active / np.sqrt(np.mean(added**2)))
    assert measured == pytest.approx(snr, abs=0.3)
    assert result.measured_snr_db == pytest.approx(snr, abs=0.01)


def test_snr_uses_active_speech_not_the_whole_clip() -> None:
    speech = _speechlike()
    mask = nm.active_mask(speech)
    assert 0.3 < mask.mean() < 0.7  # the detector found the pauses
    assert nm.active_rms(speech, mask) > 1.3 * np.sqrt(np.mean(speech**2))


def test_same_seed_is_byte_identical_and_different_seed_differs() -> None:
    speech, noise = _speechlike(), pink_noise(10.0, seed=3)
    first = mix_at_snr(speech, noise, 10.0, seed=5)
    assert mix_at_snr(speech, noise, 10.0, seed=5).wav == first.wav
    other = mix_at_snr(speech, noise, 10.0, seed=6)
    assert other.wav != first.wav and other.noise_offset != first.noise_offset


def test_pink_noise_is_seeded_and_has_falling_spectrum() -> None:
    assert np.array_equal(pink_noise(2.0, 4), pink_noise(2.0, 4))
    power = np.abs(np.fft.rfft(pink_noise(8.0, 4))) ** 2
    low, high = power[100:1000].mean(), power[40000:50000].mean()
    assert low > 10 * high


def test_loud_mix_is_scaled_not_clipped_and_keeps_its_snr() -> None:
    speech = _speechlike() * 3.0  # peaks near 0.9, plus noise would pass full scale
    result = mix_at_snr(speech, pink_noise(10.0, seed=3), 5.0, seed=1)
    assert result.peak_scale < 1.0
    assert np.max(np.abs(_wav_samples(result.wav))) <= nm.PEAK_CEILING + 1e-3
    assert result.measured_snr_db == pytest.approx(5.0, abs=0.01)


def test_silent_speech_is_refused() -> None:
    with pytest.raises(NoiseMixError, match="silent"):
        mix_at_snr(np.zeros(nm.RATE * 2), pink_noise(5.0, 1), 10.0, seed=1)


def test_noise_shorter_than_speech_is_refused() -> None:
    with pytest.raises(NoiseMixError, match="shorter"):
        mix_at_snr(_speechlike(4.0), pink_noise(2.0, 1), 10.0, seed=1)


def test_silent_noise_is_refused() -> None:
    with pytest.raises(NoiseMixError, match="noise window is silent"):
        mix_at_snr(_speechlike(), np.zeros(nm.RATE * 10), 10.0, seed=1)


def test_too_short_speech_and_out_of_range_snr_are_refused() -> None:
    with pytest.raises(NoiseMixError, match="shorter than"):
        mix_at_snr(_speechlike(0.2), pink_noise(5.0, 1), 10.0, seed=1)
    with pytest.raises(NoiseMixError, match="outside"):
        mix_at_snr(_speechlike(), pink_noise(10.0, 1), 80.0, seed=1)


def test_read_wav_rejects_wrong_rate_and_garbage() -> None:
    with pytest.raises(NoiseMixError, match="16 kHz"):
        nm.read_wav(make_wav(1.0, rate=8000))
    with pytest.raises(NoiseMixError, match="PCM WAV"):
        nm.read_wav(b"not a wav")


def test_wav_round_trip_and_derive_seed_is_stable() -> None:
    samples = _speechlike(1.0)
    assert np.allclose(nm.read_wav(nm.write_wav(samples)), samples, atol=1 / 32768)
    assert nm.derive_seed(1, "g01", 10) == nm.derive_seed(1, "g01", 10)
    assert nm.derive_seed(1, "g01", 10) != nm.derive_seed(1, "g01", 5)
