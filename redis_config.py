import os
import redis
import json

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

def get_session_history(user_id):
    redis_client = get_redis_client()
    try:
        cached_history = redis_client.get(f"chat_history:{user_id}")
        if cached_history:
            return json.loads(cached_history)
    except redis.exceptions.ConnectionError:
        print("Failed to get session history from Redis cache due to connection error")
    return []
