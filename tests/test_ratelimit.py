from saathi.ratelimit import SlidingWindowLimiter


def test_blocks_over_limit_then_allows_after_window() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, window_s=60, clock=lambda: now[0])

    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    now[0] = 61.0
    assert limiter.allow("a")


def test_keys_are_independent() -> None:
    limiter = SlidingWindowLimiter(1)
    assert limiter.allow("a")
    assert limiter.allow("b")
    assert not limiter.allow("a")


def test_idle_keys_are_swept_after_the_window() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, window_s=60, clock=lambda: now[0])
    for i in range(1000):
        assert limiter.allow(f"ip-{i}")
    assert limiter.tracked_keys() == 1000

    now[0] = 61.0
    assert limiter.allow("fresh")  # the call after the window triggers the sweep

    assert limiter.tracked_keys() == 1


def test_a_key_with_a_recent_hit_survives_the_sweep_and_keeps_its_count() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, window_s=60, clock=lambda: now[0])
    assert limiter.allow("busy")
    assert limiter.allow("idle")
    now[0] = 50.0
    assert limiter.allow("busy")  # newest hit at 50
    now[0] = 61.0  # sweep: idle's newest hit (0) is outside the window, busy's (50) is not

    assert limiter.allow("busy")  # the hit at 0 expired; the one at 50 still counts (2 of 2)
    assert limiter.tracked_keys() == 1  # the sweep ran and dropped only "idle"
    assert not limiter.allow("busy")


def test_sweeping_never_lets_a_blocked_key_through_early() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(1, window_s=60, clock=lambda: now[0])
    assert limiter.allow("a")
    now[0] = 59.0
    assert not limiter.allow("a")
    now[0] = 61.0
    assert limiter.allow("a")
    assert not limiter.allow("a")
