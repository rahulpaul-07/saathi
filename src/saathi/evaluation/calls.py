"""Gnani call budget and pacing for the evaluation. Every call spends credit and counts toward a
rate limit (about 4 calls in 10 s returned 429), so nothing here sends a call it has not counted.
"""

import asyncio
import json
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from saathi.config import Settings
from saathi.gnani import GnaniClient

GNANI_CALL_CAP = 290  # across every eval command, persisted in the ledger (see docs/DESIGN.md 11)

# The call plan, by command. A latency turn is one STT and one TTS call; the first turn is a
# warm-up (connection setup) and is not reported.
SYNTH_CLIPS = 40
LATENCY_TURNS = 41
REAL_CLIPS = 10
CALLS_PER_TURN = 2
PLANNED_CALLS = {
    "synth": SYNTH_CLIPS,
    "latency": LATENCY_TURNS * CALLS_PER_TURN,
    "stt-real": REAL_CLIPS,
}

# Stay under the observed limit with margin: at most 3 calls in any 10 s window.
MAX_CALLS_PER_WINDOW = 3
WINDOW_S = 10.0


class BudgetExceededError(RuntimeError):
    """Sending one more call would pass the cap."""


class SlidingWindowLimiter:
    """Allows at most `max_calls` in any `window_s`. Callers reserve calls before making them.

    A turn reserves both of its calls when it starts, which is conservative (the second call
    really happens later) and keeps the waiting outside the timed part of the turn.
    """

    def __init__(
        self,
        max_calls: int = MAX_CALLS_PER_WINDOW,
        window_s: float = WINDOW_S,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._max_calls = max_calls
        self._window_s = window_s
        self._clock = clock
        self._sleep = sleep
        self._stamps: deque[float] = deque()

    async def acquire(self, calls: int = 1) -> None:
        if not 1 <= calls <= self._max_calls:
            raise ValueError(f"cannot reserve {calls} calls in a window of {self._max_calls}")
        while True:
            now = self._clock()
            while self._stamps and self._stamps[0] <= now - self._window_s:
                self._stamps.popleft()
            if len(self._stamps) + calls <= self._max_calls:
                self._stamps.extend([now] * calls)
                return
            await self._sleep(self._stamps[0] + self._window_s - now)


class CallLedger:
    """Persistent count of Gnani calls spent by the evaluation, by command."""

    def __init__(self, path: Path, cap: int = GNANI_CALL_CAP) -> None:
        self._path = path
        self._cap = cap
        self._spent: dict[str, int] = {}
        if path.exists():
            self._spent = {str(k): int(v) for k, v in json.loads(path.read_text()).items()}

    @property
    def total(self) -> int:
        return sum(self._spent.values())

    @property
    def cap(self) -> int:
        return self._cap

    def spent(self, label: str) -> int:
        return self._spent.get(label, 0)

    def spend(self, label: str, calls: int = 1) -> None:
        """Count a call before it is made; raises instead of letting the cap be passed."""
        if self.total + calls > self._cap:
            raise BudgetExceededError(f"call cap of {self._cap} reached ({self.total} spent)")
        self._spent[label] = self.spent(label) + calls
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._spent, indent=2))
        os.replace(temporary, self._path)


class MeteredGnani(GnaniClient):
    """The real client, but every HTTP call is counted in the ledger first (retries included)."""

    def __init__(
        self,
        settings: Settings,
        ledger: CallLedger,
        label: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(settings, client)
        self._ledger = ledger
        self._label = label

    async def _post(self, path: str, **kwargs: object) -> httpx.Response:
        self._ledger.spend(self._label)
        return await super()._post(path, **kwargs)


def planned_total() -> int:
    return sum(PLANNED_CALLS.values())
