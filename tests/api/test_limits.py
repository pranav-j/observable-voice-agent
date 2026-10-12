"""Call limits for the demo: per IP per hour, and per day."""

from datetime import UTC, datetime

from voice_order.api.limits import CallLimiter

NOON = datetime(2026, 10, 12, 12, 0, tzinfo=UTC).timestamp()


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_no_limits_by_default() -> None:
    limiter = CallLimiter(0, 0, clock=Clock(NOON))
    assert all(limiter.try_start("1.2.3.4") is None for _ in range(100))


def test_an_ip_gets_its_calls_back_an_hour_after_each_one() -> None:
    clock = Clock(NOON)
    limiter = CallLimiter(per_ip_per_hour=2, per_day=0, clock=clock)
    assert limiter.try_start("1.2.3.4") is None
    clock.now += 600
    assert limiter.try_start("1.2.3.4") is None
    refusal = limiter.try_start("1.2.3.4")
    assert refusal is not None
    assert refusal.retry_after_seconds == 3000 + 1  # the first call leaves the window then
    assert limiter.try_start("5.6.7.8") is None  # other callers aren't affected
    clock.now = NOON + 3600
    assert limiter.try_start("1.2.3.4") is None


def test_daily_cap_resets_at_utc_midnight() -> None:
    clock = Clock(NOON)
    limiter = CallLimiter(per_ip_per_hour=0, per_day=2, clock=clock)
    assert limiter.try_start("a") is None
    assert limiter.try_start("b") is None
    refusal = limiter.try_start("c")
    assert refusal is not None
    assert refusal.retry_after_seconds == 12 * 3600 + 1
    assert "today" in refusal.reason
    clock.now = NOON + 12 * 3600
    assert limiter.try_start("c") is None


def test_refused_calls_dont_use_up_the_allowance() -> None:
    clock = Clock(NOON)
    limiter = CallLimiter(per_ip_per_hour=1, per_day=2, clock=clock)
    assert limiter.try_start("a") is None
    for _ in range(5):
        assert limiter.try_start("a") is not None
    assert limiter.try_start("b") is None  # the day still had room for a second call
