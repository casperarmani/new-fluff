import os
import redis

def get_redis_client():
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL environment variable is not set")
    return redis.from_url(redis_url)

def test_redis_connection():
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        print("Successfully connected to Redis")
        return True
    except Exception as e:
        print(f"Failed to connect to Redis: {str(e)}")
        return False
