import threading
import time
from collections import deque


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> int | None:
        timestamp = time.monotonic() if now is None else now
        cutoff = timestamp - window_seconds
        with self._lock:
            if len(self._requests) >= 1_000:
                self._requests = {
                    request_key: request_times
                    for request_key, request_times in self._requests.items()
                    if request_times and request_times[-1] > cutoff
                }
            requests = self._requests.setdefault(key, deque())
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= limit:
                return max(1, int(window_seconds - (timestamp - requests[0])))
            requests.append(timestamp)
        return None


public_intake_rate_limiter = FixedWindowRateLimiter()
