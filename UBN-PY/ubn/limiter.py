import asyncio
import time

class AsyncTokenBucketLimiter:
    def __init__(self, rate_per_minute: int = 60, burst: int | None = None):
        self.rate_per_minute = max(1, int(rate_per_minute))
        self.capacity = max(1, int(burst or rate_per_minute))
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def update(self, rate_per_minute: int | None = None, burst: int | None = None) -> None:
        async with self._lock:
            if rate_per_minute is not None:
                self.rate_per_minute = max(1, int(rate_per_minute))
            if burst is not None:
                self.capacity = max(1, int(burst))
            self.tokens = min(self.tokens, float(self.capacity))

    async def acquire(self, tokens: float = 1.0, block: bool = True) -> bool:
        tokens = float(tokens)
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                if not block:
                    return False
                missing = tokens - self.tokens
                rate_per_sec = self.rate_per_minute / 60.0
                wait_seconds = max(0.01, missing / rate_per_sec)
            await asyncio.sleep(wait_seconds)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed <= 0:
            return
        rate_per_sec = self.rate_per_minute / 60.0
        self.tokens = min(self.capacity, self.tokens + elapsed * rate_per_sec)
        self.last_refill = now