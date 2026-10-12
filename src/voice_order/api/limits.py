"""Limits on starting calls, for a public demo: calls per IP per hour, and calls per day.

Counts live in memory, so they reset when the backend restarts. That's fine for a demo
on one instance (see docs/adr/0008-demo-limits.md). A limit of 0 means no limit.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

HOUR = 3600.0


@dataclass(frozen=True)
class Refusal:
    reason: str
    retry_after_seconds: int


class CallLimiter:
    def __init__(
        self, per_ip_per_hour: int, per_day: int, clock: Callable[[], float] = time.time
    ) -> None:
        self.per_ip_per_hour = per_ip_per_hour
        self.per_day = per_day
        self._clock = clock
        self._recent: defaultdict[str, deque[float]] = defaultdict(deque)
        self._day = ""
        self._today = 0
        self._lock = threading.Lock()

    def try_start(self, ip: str) -> Refusal | None:
        """Count a call from `ip`, or say why it can't start. Refused calls aren't counted."""
        with self._lock:
            now = self._clock()
            day = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
            if day != self._day:
                self._day, self._today = day, 0
            recent = self._recent[ip]
            while recent and recent[0] <= now - HOUR:
                recent.popleft()
            if self.per_day and self._today >= self.per_day:
                midnight = datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() + 24 * HOUR
                return Refusal(
                    "The demo has taken all its calls for today. Try again tomorrow.",
                    int(midnight - now) + 1,
                )
            if self.per_ip_per_hour and len(recent) >= self.per_ip_per_hour:
                return Refusal(
                    "Too many calls from your network in the last hour. Try again later.",
                    int(recent[0] + HOUR - now) + 1,
                )
            recent.append(now)
            self._today += 1
            return None
