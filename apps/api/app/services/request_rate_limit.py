import ipaddress
import threading
import time
from collections import OrderedDict, deque

from fastapi import Request


class RequestBodyTooLargeError(ValueError):
    """Raised as soon as a streamed request body exceeds its configured limit."""


async def read_bounded_request_body(request: Request, *, max_bytes: int) -> bytes:
    """Read an ASGI request without ever buffering more than ``max_bytes``."""
    content_length = request.headers.get("content-length", "").strip()
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > max_bytes:
            raise RequestBodyTooLargeError

    body = bytearray()
    async for chunk in request.stream():
        if len(chunk) > max_bytes - len(body):
            raise RequestBodyTooLargeError
        body.extend(chunk)
    return bytes(body)


class FixedWindowRateLimiter:
    def __init__(self, *, max_keys: int = 2_048) -> None:
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()
        self._max_keys = max(1, max_keys)
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
            requests = self._requests.get(key)
            if requests is None:
                if len(self._requests) >= self._max_keys:
                    self._requests.popitem(last=False)
                requests = deque()
                self._requests[key] = requests
            else:
                self._requests.move_to_end(key)
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= limit:
                return max(1, int(window_seconds - (timestamp - requests[0])))
            requests.append(timestamp)
        return None

    @property
    def tracked_key_count(self) -> int:
        with self._lock:
            return len(self._requests)


def trusted_client_address(request: Request, *, production: bool) -> str:
    """Resolve an edge-vetted address without ever trusting caller-controlled XFF."""
    if production:
        # Uvicorn/Render resolves its trusted proxy chain into request.client.
        # Direct origin callers can forge both XFF and Cloudflare-named headers, so
        # neither is identity evidence at the application layer.
        if request.client and request.client.host:
            try:
                peer_address = ipaddress.ip_address(request.client.host)
            except ValueError:
                pass
            else:
                if peer_address.is_global:
                    return str(peer_address)
        return "edge-unknown"
    if request.client and request.client.host:
        return request.client.host[:128]
    return "unknown"


public_intake_rate_limiter = FixedWindowRateLimiter()
zapier_lead_rate_limiter = FixedWindowRateLimiter()
