import asyncio
import time
from collections import defaultdict, deque


CHATBOT_REQUESTS_PER_MINUTE = 10 
RATE_LIMIT_WINDOW_SECONDS = 60


class ChatRateLimiter:
    """
    Simple in-memory per-user sliding-window rate limiter.

    Suitable for the current single-instance deployment.
    If the backend is later deployed across multiple workers or servers,
    this can be replaced with Redis-based rate limiting.
    """

    def __init__(
        self,
        limit: int = CHATBOT_REQUESTS_PER_MINUTE,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        self.limit = limit
        self.window_seconds = window_seconds

        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, user_id: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            requests = self._requests[user_id]

            while requests and requests[0] <= cutoff:
                requests.popleft()

            if len(requests) >= self.limit:
                return False

            requests.append(now)
            return True


chat_rate_limiter = ChatRateLimiter()