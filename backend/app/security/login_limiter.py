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

# Hard cap on tracked keys. The username is attacker-controlled, so without
# a cap a spray of random names would grow the map for the life of the
# process. Pruning happens on write, not on read, so a read for an unknown
# key never allocates an entry.
MAX_TRACKED_KEYS = _env_int("AUTH_LOGIN_MAX_TRACKED_KEYS", 10_000)


class LoginRateLimiter:
    """Thread-safe per-key sliding-window limiter for failed logins."""

    def __init__(
        self,
        limit: int = LOGIN_MAX_ATTEMPTS,
        window_seconds: int = LOGIN_WINDOW_SECONDS,
        max_keys: int = MAX_TRACKED_KEYS,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _key(self, client: str, username: str) -> str:
        # Username is case-folded: Tally logins are case-sensitive, but a
        # brute-forcer should not get a fresh budget by changing case.
        return f"{(client or '').strip()}|{(username or '').strip().casefold()}"

    def _prune_locked(self, now: float) -> None:
        """Drop keys whose attempts have all fallen outside the window."""
        cutoff = now - self.window_seconds

        for key in list(self._attempts.keys()):
            attempts = self._attempts[key]

            while attempts and attempts[0] <= cutoff:
                attempts.popleft()

            if not attempts:
                self._attempts.pop(key, None)

    def is_blocked(self, client: str, username: str) -> bool:
        """True when this key has exhausted its attempts in the window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        key = self._key(client, username)

        with self._lock:
            # .get() rather than indexing: a lookup for an unseen key must
            # not create a defaultdict entry.
            attempts = self._attempts.get(key)

            if not attempts:
                return False

            while attempts and attempts[0] <= cutoff:
                attempts.popleft()

            if not attempts:
                self._attempts.pop(key, None)
                return False

            return len(attempts) >= self.limit

    def register_failure(self, client: str, username: str) -> None:
        """Record one failed attempt against the key."""
        key = self._key(client, username)
        now = time.monotonic()

        with self._lock:
            self._prune_locked(now)

            # Still bounded after pruning: drop the oldest key rather than
            # letting a key spray exceed the cap.
            while len(self._attempts) >= self.max_keys and key not in self._attempts:
                oldest = min(
                    self._attempts,
                    key=lambda name: (
                        self._attempts[name][0] if self._attempts[name] else now
                    ),
                )
                self._attempts.pop(oldest, None)

            attempts = self._attempts.get(key)
            if attempts is None:
                attempts = deque()
                self._attempts[key] = attempts

            attempts.append(now)

    def reset(self, client: str, username: str) -> None:
        """Forget the failures for a key (called after a successful login)."""
        with self._lock:
            self._attempts.pop(self._key(client, username), None)


login_rate_limiter = LoginRateLimiter()
