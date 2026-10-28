from pathlib import Path

import httpx
import pytest

from saathi.config import Settings
from saathi.evaluation.calls import (
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _limiter(clock: FakeClock) -> SlidingWindowLimiter:
    return SlidingWindowLimiter(3, 10.0, clock=clock, sleep=clock.sleep)


async def test_limiter_lets_a_turn_through_then_waits_for_the_window() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)
    await limiter.acquire(2)
    assert clock.slept == []
    await limiter.acquire(2)  # 2 + 2 > 3 in the window: must wait for the first turn to age out
    assert clock.slept == [10.0]


async def test_limiter_allows_single_calls_up_to_the_window_limit() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)
    for _ in range(3):
        await limiter.acquire()
    assert clock.slept == []
    await limiter.acquire()
    assert clock.slept == [10.0]


async def test_limiter_never_exceeds_three_calls_in_any_ten_seconds() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)
    stamps: list[float] = []
    for _ in range(12):
        await limiter.acquire(2)
        stamps += [clock.now, clock.now]
    for i, start in enumerate(stamps):
        assert sum(1 for s in stamps[i:] if s < start + 10.0) <= 3


async def test_limiter_rejects_a_reservation_larger_than_the_window() -> None:
    with pytest.raises(ValueError):
        await _limiter(FakeClock()).acquire(4)


def test_ledger_counts_persists_and_refuses_past_the_cap(tmp_path: Path) -> None:
    path = tmp_path / "state" / "ledger.json"
    ledger = CallLedger(path, cap=3)
    ledger.spend("synth", 2)
    ledger.spend("latency")
    with pytest.raises(BudgetExceededError):
        ledger.spend("latency")
    reloaded = CallLedger(path, cap=3)
    assert reloaded.total == 3 and reloaded.spent("synth") == 2
    with pytest.raises(BudgetExceededError):
        reloaded.spend("synth")


async def test_metered_client_counts_each_call_and_blocks_at_the_cap(tmp_path: Path) -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        return httpx.Response(200, json={"success": True, "transcript": "hello"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://x.test")
    ledger = CallLedger(tmp_path / "ledger.json", cap=1)
    client = MeteredGnani(Settings(gnani_api_key="test-key"), ledger, "stt-real", http)  # type: ignore[arg-type]
    assert await client.transcribe(b"wav", "a.wav", "bn-IN") == "hello"
    assert ledger.spent("stt-real") == 1
    with pytest.raises(BudgetExceededError):
        await client.transcribe(b"wav", "a.wav", "bn-IN")
    assert len(sent) == 1  # the second call never left the machine
    await client.aclose()
