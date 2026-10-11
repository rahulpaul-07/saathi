import pytest

from saathi.evaluation.calls import SlidingWindowLimiter
from saathi.evaluation.translation import evaluate_sentence, summarize
from saathi.evaluation.turns import call_with_retry, measure_turn, summarize_latency
from saathi.gnani import GnaniError
from saathi.pipeline import Timings
from saathi.translate import TranslationResult


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class FlakyGnani:
    """Fails the first `failures` STT calls with `status`, then behaves."""

    def __init__(self, failures: int = 0, status: int = 429) -> None:
        self.failures, self.status = failures, status

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        if self.failures > 0:
            self.failures -= 1
            raise GnaniError("boom", self.status)
        return "namaskar"

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        return b"wav"

    async def transcribe_once(self) -> str:
        return await self.transcribe(b"x", "a.wav", "bn-IN")


class EchoTranslator:
    def __init__(self, output: str = "ಬೇಗ ಬೇಗ") -> None:
        self.output = output

    def translate(self, text: str, src: str, tgt: str) -> str:
        return self.output


async def _measure(gnani: FlakyGnani, translator: EchoTranslator, clock: FakeClock):  # type: ignore[no-untyped-def]
    limiter = SlidingWindowLimiter(3, 10.0, clock=clock, sleep=clock.sleep)
    return await measure_turn(
        b"x",
        "bn",
        "kn",
        gnani,  # type: ignore[arg-type]
        translator,
        limiter,
        sleep=clock.sleep,
    )


async def test_clean_turn_has_timings_and_no_retries() -> None:
    outcome = await _measure(FlakyGnani(), EchoTranslator(), FakeClock())
    assert outcome.failure is None and outcome.retries == 0
    assert outcome.timings is not None and outcome.translation == "ಬೇಗ ಬೇಗ"


async def test_rate_limited_turn_is_retried_but_excluded_from_latency() -> None:
    clock = FakeClock()
    outcome = await _measure(FlakyGnani(failures=1), EchoTranslator(), clock)
    assert outcome.failure is None
    assert outcome.retries == 1
    assert outcome.timings is None  # a retried turn is not a clean latency sample
    assert clock.slept == [10.0]  # the backoff


async def test_persistent_429_gives_up_after_three_retries() -> None:
    clock = FakeClock()
    outcome = await _measure(FlakyGnani(failures=99), EchoTranslator(), clock)
    assert outcome.failure == "rate limited" and outcome.retries == 3
    assert clock.slept == [10.0, 20.0, 30.0]  # backoff only: the limiter window had expired


async def test_other_gnani_errors_are_not_retried() -> None:
    outcome = await _measure(FlakyGnani(failures=1, status=500), EchoTranslator(), FakeClock())
    assert outcome.failure == "gnani status 500" and outcome.retries == 0


async def test_unreliable_translation_is_recorded_with_its_transcript() -> None:
    outcome = await _measure(FlakyGnani(), EchoTranslator("ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ"), FakeClock())
    assert outcome.failure == "unreliable translation" and outcome.transcript == "namaskar"


async def test_call_with_retry_retries_429_then_succeeds_and_reraises_others() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(3, 10.0, clock=clock, sleep=clock.sleep)
    gnani = FlakyGnani(failures=2)
    text, retries = await call_with_retry(
        lambda: gnani.transcribe(b"x", "a.wav", "bn-IN"), limiter, sleep=clock.sleep
    )
    assert (text, retries) == ("namaskar", 2)
    assert clock.slept == [10.0, 20.0]
    with pytest.raises(GnaniError):
        await call_with_retry(
            FlakyGnani(failures=1, status=500).transcribe_once, limiter, sleep=clock.sleep
        )


def test_summarize_latency_reports_n_and_percentiles_per_stage() -> None:
    samples = [Timings(100.0 * i, 10.0, 20.0, 100.0 * i + 30) for i in range(1, 5)]
    summary = summarize_latency(samples)
    assert summary["stt_ms"].n == 4 and summary["stt_ms"].p50 == 250
    assert summary["stt_ms"].p95 == pytest.approx(385)
    assert summary["translate_ms"].max == 10


def test_stt_scoring_and_summary_normalize_and_split_head_from_tail() -> None:
    from saathi.evaluation.stt import score_transcript, summarize_stt

    references = ["আমি ভালো আছি আজ", "এটি একটি পরীক্ষা হয়"]
    rows = [
        score_transcript(0, "আমি, ভালো আছি আজ।", references[0]),  # punctuation only differs
        score_transcript(1, "সেই শর্ট পরীক্ষা হয়", references[1]),  # first words garbled
    ]
    assert rows[0].cer == 0 and rows[0].head_missed == 0
    assert rows[1].head_missed == 2
    summary = summarize_stt(rows, references)
    assert summary.n == 2 and summary.head_rate == 0.5 and summary.cer_median == summary.cer_mean
    assert summary.tail_words == 4 and summary.tail_missed == 0


class FakeStatsTranslator:
    def __init__(self, result: TranslationResult) -> None:
        self.result = result

    def translate_with_stats(self, text: str, src: str, tgt: str) -> TranslationResult:
        return self.result


def test_evaluate_sentence_flags_capped_and_repeated_outputs() -> None:
    ok = evaluate_sentence(
        FakeStatsTranslator(TranslationResult("the cat sat", 4, 5, 18, capped=False)),
        0, "src", "the cat sat", "bn", "kn",
    )  # fmt: skip
    assert not ok.flagged and ok.ratio == 1.25 and ok.chrf == pytest.approx(100)
    capped = evaluate_sentence(
        FakeStatsTranslator(TranslationResult("x", 4, 18, 18, capped=True)),
        1, "src", "ref", "bn", "kn",
    )  # fmt: skip
    assert capped.flagged and not capped.repeated
    looped = evaluate_sentence(
        FakeStatsTranslator(TranslationResult("a b a b a b a b", 4, 9, 18, capped=False)),
        2, "src", "ref", "bn", "kn",
    )  # fmt: skip
    assert looped.flagged and looped.repeated


def test_summarize_counts_flags_and_corpus_score() -> None:
    translator = FakeStatsTranslator(TranslationResult("the cat sat", 4, 5, 18, capped=False))
    rows = [evaluate_sentence(translator, i, "s", "the cat sat", "bn", "kn") for i in range(3)]
    summary = summarize(rows, ["the cat sat"] * 3)
    assert summary.n == 3 and summary.flagged == 0
    assert summary.chrf_pp == pytest.approx(100)
