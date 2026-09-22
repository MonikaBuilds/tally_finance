import asyncio
from collections import defaultdict


MAX_CONCURRENT_REQUESTS_PER_USER = 1


class UserConcurrencyLimiter:
    """
    Limit how many chatbot requests one user can process at the same time.

    This protects shared Gemini and Tally resources from being occupied
    by a single user during sudden bursts of requests.
    """

    def __init__(
        self,
        max_concurrent: int = MAX_CONCURRENT_REQUESTS_PER_USER,
    ):
        self.max_concurrent = max_concurrent

        # Each user gets their own semaphore.
        # This keeps the concurrency limit independent per authenticated user.
        self._user_semaphores: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self.max_concurrent)
        )

        # Protect semaphore creation/access when many requests arrive together.
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        user_id: str,
        timeout: float = 1.0,
    ) -> bool:
        """
        Try to reserve one execution slot for a user.

        Returns False when the user already has too many active requests
        and no slot becomes available within the timeout.
        """

        async with self._lock:
            semaphore = self._user_semaphores[user_id]

        try:
            await asyncio.wait_for(
                semaphore.acquire(),
                timeout=timeout,
            )
            return True

        except asyncio.TimeoutError:
            return False

    async def release(
        self,
        user_id: str,
    ) -> None:
        """
        Release a previously reserved execution slot.
        """

        async with self._lock:
            semaphore = self._user_semaphores.get(user_id)

        if semaphore is not None:
            semaphore.release()


user_concurrency_limiter = UserConcurrencyLimiter()