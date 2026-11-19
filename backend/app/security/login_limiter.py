"""
Brute-force protection for the login endpoint.

A small in-process sliding window, keyed by client address and username.
Mirrors the chatbot rate limiter's approach (asyncio-free here because the
login route is a synchronous endpoint), and every limit is configurable
through the environment so nothing is baked into the code.

A successful login clears the counter for that key, so a legitimate user
who mistypes once is not locked out.
"""

import os
import threading
import time
from collections import defaultdict, deque


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "").strip() or default))
    except ValueError:
        return default


LOGIN_MAX_ATTEMPTS = _env_int("AUTH_LOGIN_MAX_ATTEMPTS", 10)
LOGIN_WINDOW_SECONDS = _env_int("AUTH_LOGIN_WINDOW_SECONDS", 300)


class LoginRateLimiter:
    """Thread-safe per-key sliding-window limiter for failed logins."""

    def __init__(
        self,
        limit: int = LOGIN_MAX_ATTEMPTS,
        window_seconds: int = LOGIN_WINDOW_SECONDS,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _key(self, client: str, username: str) -> str:
        # Username is case-folded: Tally logins are case-sensitive, but a
        # brute-forcer should not get a fresh budget by changing case.
        return f"{(client or '').strip()}|{(username or '').strip().casefold()}"

    def is_blocked(self, client: str, username: str) -> bool:
        """True when this key has exhausted its attempts in the window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        key = self._key(client, username)

        with self._lock:
            attempts = self._attempts[key]

            while attempts and attempts[0] <= cutoff:
                attempts.popleft()

            return len(attempts) >= self.limit

    def register_failure(self, client: str, username: str) -> None:
        """Record one failed attempt against the key."""
        key = self._key(client, username)

        with self._lock:
            self._attempts[key].append(time.monotonic())

    def reset(self, client: str, username: str) -> None:
        """Forget the failures for a key (called after a successful login)."""
        with self._lock:
            self._attempts.pop(self._key(client, username), None)


login_rate_limiter = LoginRateLimiter()
