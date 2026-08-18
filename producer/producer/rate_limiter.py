import time


class RateLimiter:
    """Fixed-cadence pacing on the monotonic clock, targeting an aggregate
    rate across however many events are ticked through it. Deliberately does
    not reproduce original inter-arrival gaps (REQUIREMENTS.md Sec 5.1: replay
    rate is configurable and independent of original timestamps).
    """

    def __init__(self, rate_per_sec: float):
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be positive")
        self._interval = 1.0 / rate_per_sec
        self._next_tick = time.monotonic()

    def wait_for_next_tick(self) -> None:
        now = time.monotonic()
        sleep_for = self._next_tick - now
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._next_tick += self._interval
        # If we've fallen far behind (e.g. a slow publish stalled the loop),
        # resync to now instead of bursting to catch up.
        if self._next_tick < time.monotonic() - self._interval:
            self._next_tick = time.monotonic()
