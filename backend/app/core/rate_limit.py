import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import settings


class RateLimiter:
    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def __call__(self, request: Request):
        key = request.client.host if request.client else "unknown"
        tick = time.monotonic()
        with self.lock:
            # Prune old keys too; do not retain an unbounded IP map.
            for old_key in list(self.hits):
                queue = self.hits[old_key]
                while queue and queue[0] <= tick - settings.auth_rate_window:
                    queue.popleft()
                if not queue:
                    del self.hits[old_key]
            queue = self.hits[key]
            if len(queue) >= settings.auth_rate_limit:
                retry = max(1, int(settings.auth_rate_window - (tick - queue[0])) + 1)
                raise HTTPException(
                    429,
                    "Too many attempts. Please try again shortly.",
                    headers={"Retry-After": str(retry)},
                )
            queue.append(tick)


limiter = RateLimiter()
