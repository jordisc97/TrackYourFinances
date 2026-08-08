from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request, status

from app.config import get_settings


class AuthRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, request: Request, bucket: str) -> None:
        limit = get_settings().auth_rate_limit_per_minute
        window = 60.0
        client = request.client.host if request.client else "unknown"
        key = f"{bucket}:{client}"
        now = monotonic()
        stamps = self._hits[key]
        while stamps and now - stamps[0] > window:
            stamps.popleft()
        if len(stamps) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts. Try again in a minute.")
        stamps.append(now)


auth_rate_limiter = AuthRateLimiter()
