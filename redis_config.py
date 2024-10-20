import os
import redis
import json
import logging
from typing import List, Dict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_redis_client():
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL environment variable is not set")
    return redis.from_url(redis_url)

def test_redis_connection():
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        logger.info("Successfully connected to Redis")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        return False

def get_session_history(user_id: str, limit: int = 10) -> List[Dict]:
    redis_client = get_redis_client()
    try:
        cached_history = redis_client.lrange(f"chat_history:{user_id}", 0, limit - 1)
        if cached_history:
            return [json.loads(message.decode('utf-8')) for message in cached_history]
    except redis.exceptions.ConnectionError:
        logger.error("Failed to get session history from Redis cache due to connection error")
    except Exception as e:
        logger.error(f"Error retrieving session history: {str(e)}")
    return []

def update_chat_history(user_id: str, message: Dict):
    redis_client = get_redis_client()
    try:
        key = f"chat_history:{user_id}"
        redis_client.lpush(key, json.dumps(message))
        redis_client.ltrim(key, 0, 9)  # Keep only the last 10 messages
    except redis.exceptions.ConnectionError:
        logger.error("Failed to update chat history in Redis cache due to connection error")
    except Exception as e:
        logger.error(f"Error updating chat history: {str(e)}")

def clear_chat_history(user_id: str):
    redis_client = get_redis_client()
    try:
        redis_client.delete(f"chat_history:{user_id}")
    except redis.exceptions.ConnectionError:
        logger.error("Failed to clear chat history in Redis cache due to connection error")
    except Exception as e:
        logger.error(f"Error clearing chat history: {str(e)}")
