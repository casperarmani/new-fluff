import os
import redis
import logging
import json
from typing import Any, Optional, Callable
import asyncio

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is not set")

# Set TTL for chat sessions (e.g., 1 hour)
CHAT_SESSION_TTL = 3600

# Batch size for database writes
DB_WRITE_BATCH_SIZE = 10

# Create a connection pool
redis_pool = redis.ConnectionPool.from_url(REDIS_URL, max_connections=10)

def get_redis_client():
    return redis.Redis(connection_pool=redis_pool)

def test_redis_connection():
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        logger.info("Successfully connected to Redis")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        return False

async def cache_set(key: str, value: Any, ttl: int = CHAT_SESSION_TTL) -> None:
    redis_client = get_redis_client()
    try:
        serialized_value = json.dumps(value)
        await asyncio.to_thread(redis_client.setex, key, ttl, serialized_value)
    except Exception as e:
        logger.error(f"Error setting cache for key {key}: {str(e)}")

async def cache_get(key: str) -> Optional[Any]:
    redis_client = get_redis_client()
    try:
        value = await asyncio.to_thread(redis_client.get, key)
        return json.loads(value) if value else None
    except Exception as e:
        logger.error(f"Error getting cache for key {key}: {str(e)}")
        return None

async def cache_delete(key: str) -> None:
    redis_client = get_redis_client()
    try:
        await asyncio.to_thread(redis_client.delete, key)
    except Exception as e:
        logger.error(f"Error deleting cache for key {key}: {str(e)}")

async def write_through_cache(key: str, value: Any, db_write_func: Callable, ttl: int = CHAT_SESSION_TTL) -> None:
    try:
        # Update cache
        await cache_set(key, value, ttl)
        
        # Write to database
        await db_write_func(value)
    except Exception as e:
        logger.error(f"Error in write-through cache for key {key}: {str(e)}")
        # If there's an error, invalidate the cache
        await cache_delete(key)

async def cache_mget(keys: list) -> list:
    redis_client = get_redis_client()
    try:
        values = await asyncio.to_thread(redis_client.mget, keys)
        return [json.loads(value) if value else None for value in values]
    except Exception as e:
        logger.error(f"Error getting multiple cache keys: {str(e)}")
        return [None] * len(keys)

async def cache_mset(key_value_pairs: dict, ttl: int = CHAT_SESSION_TTL) -> None:
    redis_client = get_redis_client()
    try:
        serialized_pairs = {k: json.dumps(v) for k, v in key_value_pairs.items()}
        await asyncio.to_thread(redis_client.mset, serialized_pairs)
        for key in key_value_pairs.keys():
            await asyncio.to_thread(redis_client.expire, key, ttl)
    except Exception as e:
        logger.error(f"Error setting multiple cache keys: {str(e)}")
