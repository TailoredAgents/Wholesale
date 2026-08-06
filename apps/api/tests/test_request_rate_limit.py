from app.services.request_rate_limit import FixedWindowRateLimiter


def test_fixed_window_rate_limiter_blocks_and_recovers() -> None:
    limiter = FixedWindowRateLimiter()

    assert limiter.check("lead:one", limit=2, window_seconds=60, now=100) is None
    assert limiter.check("lead:one", limit=2, window_seconds=60, now=110) is None
    assert limiter.check("lead:one", limit=2, window_seconds=60, now=120) == 40
    assert limiter.check("lead:one", limit=2, window_seconds=60, now=161) is None


def test_fixed_window_rate_limiter_separates_clients() -> None:
    limiter = FixedWindowRateLimiter()

    assert limiter.check("lead:one", limit=1, window_seconds=60, now=100) is None
    assert limiter.check("lead:two", limit=1, window_seconds=60, now=100) is None
    assert limiter.check("lead:one", limit=1, window_seconds=60, now=101) == 59
