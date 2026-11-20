"""
Login brute-force limiter behaviour.

The limiter must keep throttling identical to before while never growing
without bound: the username is attacker-controlled, so unknown keys must
not be stored and the map must stay capped.
"""

import time

from app.security.login_limiter import LoginRateLimiter


def test_blocks_after_limit_and_reset_clears():
    limiter = LoginRateLimiter(limit=3, window_seconds=60)

    for _ in range(3):
        assert limiter.is_blocked("1.2.3.4", "admin") is False
        limiter.register_failure("1.2.3.4", "admin")

    assert limiter.is_blocked("1.2.3.4", "admin") is True

    limiter.reset("1.2.3.4", "admin")
    assert limiter.is_blocked("1.2.3.4", "admin") is False


def test_username_case_does_not_reset_the_budget():
    limiter = LoginRateLimiter(limit=2, window_seconds=60)

    limiter.register_failure("1.2.3.4", "Admin")
    limiter.register_failure("1.2.3.4", "ADMIN")

    assert limiter.is_blocked("1.2.3.4", "admin") is True


def test_unknown_key_lookup_does_not_allocate():
    limiter = LoginRateLimiter(limit=5, window_seconds=60)

    for index in range(500):
        assert limiter.is_blocked("1.2.3.4", f"spray-{index}") is False

    # A read for a name that was never registered must not create an entry.
    assert len(limiter._attempts) == 0


def test_tracked_keys_stay_bounded_on_key_spray():
    limiter = LoginRateLimiter(limit=5, window_seconds=60, max_keys=50)

    for index in range(500):
        limiter.register_failure("1.2.3.4", f"spray-{index}")

    assert len(limiter._attempts) <= 50


def test_expired_attempts_are_pruned():
    limiter = LoginRateLimiter(limit=1, window_seconds=0)

    limiter.register_failure("1.2.3.4", "admin")
    time.sleep(0.01)

    # The attempt has left the window, so it no longer blocks and is dropped.
    assert limiter.is_blocked("1.2.3.4", "admin") is False
    assert "1.2.3.4|admin" not in limiter._attempts
