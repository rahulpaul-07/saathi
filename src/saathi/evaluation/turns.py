"""Paced, retried execution of full interpreter turns, and the latency summary."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from saathi.evaluation.calls import CALLS_PER_TURN, SlidingWindowLimiter
from saathi.evaluation.metrics import percentile
from saathi.gnani import GnaniClient, GnaniError
from saathi.pipeline import NoSpeechError, Timings, UnreliableTranslationError, run_turn
from saathi.translate import Translator

log = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BACKOFF_S = 10.0
STAGES = ("stt_ms", "translate_ms", "tts_ms", "total_ms")


@dataclass(frozen=True)
class TurnOutcome:
    """One attempted turn. `timings` is set only for a turn that succeeded on its first attempt:
    a turn that was rate limited and retried is not a clean latency sample.
    """

    transcript: str | None
    translation: str | None
    timings: Timings | None
    retries: int
    failure: str | None  # None on success; otherwise a short reason


async def measure_turn(
    audio: bytes,
    src: str,
    tgt: str,
    gnani: GnaniClient,
    translator: Translator,
    limiter: SlidingWindowLimiter,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> TurnOutcome:
    """Run one turn under the call limiter, retrying Gnani 429s with a growing backoff."""
    retries = 0
    while True:
        await limiter.acquire(CALLS_PER_TURN)  # waits here, outside the timed turn
        try:
            result = await run_turn(audio, src, tgt, gnani, translator)
        except GnaniError as exc:
            if exc.status != 429:
                return TurnOutcome(None, None, None, retries, f"gnani status {exc.status}")
            if retries >= MAX_RATE_LIMIT_RETRIES:
                return TurnOutcome(None, None, None, retries, "rate limited")
            retries += 1
            log.warning("Gnani 429, retry %d of %d", retries, MAX_RATE_LIMIT_RETRIES)
            await sleep(RATE_LIMIT_BACKOFF_S * retries)
            continue
        except NoSpeechError:
            return TurnOutcome(None, None, None, retries, "no speech")
        except UnreliableTranslationError as exc:
            return TurnOutcome(exc.transcript, None, None, retries, "unreliable translation")
        timings = result.timings if retries == 0 else None
        return TurnOutcome(result.transcript, result.translation, timings, retries, None)


async def call_with_retry[T](
    make_call: Callable[[], Awaitable[T]],
    limiter: SlidingWindowLimiter,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[T, int]:
    """One paced Gnani call, retrying 429s. Returns the result and the retries it took."""
    retries = 0
    while True:
        await limiter.acquire(1)
        try:
            return await make_call(), retries
        except GnaniError as exc:
            if exc.status != 429 or retries >= MAX_RATE_LIMIT_RETRIES:
                raise
            retries += 1
            log.warning("Gnani 429, retry %d of %d", retries, MAX_RATE_LIMIT_RETRIES)
            await sleep(RATE_LIMIT_BACKOFF_S * retries)


@dataclass(frozen=True)
class StageLatency:
    n: int
    p50: float
    p95: float
    mean: float
    max: float


def summarize_latency(samples: Sequence[Timings]) -> dict[str, StageLatency]:
    """p50 and p95 per stage. With few samples p95 is close to the maximum; report `n` with it."""
    summary: dict[str, StageLatency] = {}
    for stage in STAGES:
        values = [getattr(sample, stage) for sample in samples]
        summary[stage] = StageLatency(
            n=len(values),
            p50=percentile(values, 50),
            p95=percentile(values, 95),
            mean=sum(values) / len(values),
            max=max(values),
        )
    return summary
