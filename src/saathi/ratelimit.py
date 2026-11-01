import time
from collections import defaultdict, deque
from collections.abc import Callable


class SlidingWindowLimiter:
    """In-memory per-key limiter. Fine for one process; several processes need a shared store.

    Keys (client IPs, room code and role) are never seen again once a person leaves, so idle keys
    are swept once per window: a key whose newest hit is outside the window cannot affect any
    future decision, which makes dropping it safe. The sweep is amortised over the calls.
    """

    def __init__(
        self, limit: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._next_sweep = clock() + window_s

    def allow(self, key: str) -> bool:
        now = self._clock()
        if now >= self._next_sweep:
            self._sweep(now)
        hits = self._hits[key]
        while hits and now - hits[0] >= self._window_s:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True

    def tracked_keys(self) -> int:
        return len(self._hits)

    def _sweep(self, now: float) -> None:
        idle = [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self._window_s]
        for key in idle:
            del self._hits[key]
        self._next_sweep = now + self._window_s
