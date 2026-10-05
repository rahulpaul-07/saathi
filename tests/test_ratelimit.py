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
