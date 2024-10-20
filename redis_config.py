import os
import redis

def get_redis_client():
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL environment variable is not set")
    return redis.from_url(redis_url)
