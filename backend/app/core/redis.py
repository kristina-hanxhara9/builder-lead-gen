"""Redis connection pool for caching and Celery broker."""

import redis

from app.core.config import settings

redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    retry_on_timeout=True,
)


def get_redis() -> redis.Redis:
    return redis_client
