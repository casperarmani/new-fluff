import os
import redis
import json
import logging
import time
from typing import List, Dict, Optional

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
    start_time = time.time()
    try:
        key = f"chat_history:{user_id}"
        cached_history = redis_client.lrange(key, 0, limit - 1)
        if cached_history:
            history = [json.loads(message.decode('utf-8')) for message in cached_history]
            logger.info(f"Retrieved chat history for user {user_id} from Redis cache")
        else:
            history = []
            logger.info(f"No chat history found in Redis cache for user {user_id}")
        end_time = time.time()
        logger.info(f"Redis get_session_history time: {end_time - start_time:.2f} seconds")
        return history
    except redis.exceptions.ConnectionError:
        logger.error("Failed to get session history from Redis cache due to connection error")
    except Exception as e:
        logger.error(f"Error retrieving session history: {str(e)}")
    return []

def update_chat_history(user_id: str, message: Dict):
    redis_client = get_redis_client()
    start_time = time.time()
    try:
        key = f"chat_history:{user_id}"
        redis_client.lpush(key, json.dumps(message))
        redis_client.ltrim(key, 0, 9)  # Keep only the last 10 messages
        end_time = time.time()
        logger.info(f"Redis update_chat_history time: {end_time - start_time:.2f} seconds")
    except redis.exceptions.ConnectionError:
        logger.error("Failed to update chat history in Redis cache due to connection error")
    except Exception as e:
        logger.error(f"Error updating chat history: {str(e)}")

def clear_chat_history(user_id: str):
    redis_client = get_redis_client()
    start_time = time.time()
    try:
        redis_client.delete(f"chat_history:{user_id}")
        end_time = time.time()
        logger.info(f"Redis clear_chat_history time: {end_time - start_time:.2f} seconds")
    except redis.exceptions.ConnectionError:
        logger.error("Failed to clear chat history in Redis cache due to connection error")
    except Exception as e:
        logger.error(f"Error clearing chat history: {str(e)}")

def cache_user(email: str, user_data: Dict):
    redis_client = get_redis_client()
    start_time = time.time()
    try:
        key = f"user:{email}"
        redis_client.setex(key, 3600, json.dumps(user_data))  # Cache user data for 1 hour
        end_time = time.time()
        logger.info(f"Redis cache_user time: {end_time - start_time:.2f} seconds")
    except redis.exceptions.ConnectionError:
        logger.error("Failed to cache user data in Redis due to connection error")
    except Exception as e:
        logger.error(f"Error caching user data: {str(e)}")

def get_cached_user(email: str) -> Optional[Dict]:
    redis_client = get_redis_client()
    start_time = time.time()
    try:
        key = f"user:{email}"
        cached_user = redis_client.get(key)
        end_time = time.time()
        logger.info(f"Redis get_cached_user time: {end_time - start_time:.2f} seconds")
        if cached_user:
            return json.loads(cached_user.decode('utf-8'))
    except redis.exceptions.ConnectionError:
        logger.error("Failed to get cached user data from Redis due to connection error")
    except Exception as e:
        logger.error(f"Error getting cached user data: {str(e)}")
    return None

def cache_video_analysis(user_id: str, analysis_data: List[Dict]):
    redis_client = get_redis_client()
    start_time = time.time()
    try:
        key = f"video_analysis:{user_id}"
        redis_client.setex(key, 3600, json.dumps(analysis_data))  # Cache video analysis for 1 hour
        end_time = time.time()
        logger.info(f"Redis cache_video_analysis time: {end_time - start_time:.2f} seconds")
    except redis.exceptions.ConnectionError:
        logger.error("Failed to cache video analysis in Redis due to connection error")
    except Exception as e:
        logger.error(f"Error caching video analysis: {str(e)}")

def get_cached_video_analysis(user_id: str) -> Optional[List[Dict]]:
    redis_client = get_redis_client()
    start_time = time.time()
    try:
        key = f"video_analysis:{user_id}"
        cached_analysis = redis_client.get(key)
        end_time = time.time()
        logger.info(f"Redis get_cached_video_analysis time: {end_time - start_time:.2f} seconds")
        if cached_analysis:
            return json.loads(cached_analysis.decode('utf-8'))
    except redis.exceptions.ConnectionError:
        logger.error("Failed to get cached video analysis from Redis due to connection error")
    except Exception as e:
        logger.error(f"Error getting cached video analysis: {str(e)}")
    return None
