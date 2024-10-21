import os
from redis import asyncio as aioredis
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is not set")

# Set TTL for chat sessions (e.g., 1 hour)
CHAT_SESSION_TTL = 3600

# Batch size for database writes
DB_WRITE_BATCH_SIZE = 10

async def get_redis_client():
    return await aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

async def test_redis_connection():
    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        logger.info("Successfully connected to Redis")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        return False

# Write-through cache functions
async def cache_set(key, value, ttl=CHAT_SESSION_TTL):
    redis_client = await get_redis_client()
    try:
        if isinstance(value, dict):
            value = json.dumps(value)
        await redis_client.setex(key, ttl, value)
    except Exception as e:
        logger.error(f"Error setting cache: {str(e)}")

async def cache_get(key):
    redis_client = await get_redis_client()
    try:
        value = await redis_client.get(key)
        return json.loads(value) if value else None
    except Exception as e:
        logger.error(f"Error getting cache: {str(e)}")
        return None

async def cache_delete(key):
    redis_client = await get_redis_client()
    try:
        await redis_client.delete(key)
    except Exception as e:
        logger.error(f"Error deleting cache: {str(e)}")

# Helper function for write-through caching
async def write_through_cache(key, value, db_write_func, ttl=CHAT_SESSION_TTL):
    try:
        # Update cache
        if isinstance(value, dict):
            cache_value = json.dumps(value)
        else:
            cache_value = value
        await cache_set(key, cache_value, ttl)
        
        # Write to database
        await db_write_func(value)
    except Exception as e:
        logger.error(f"Error in write-through cache: {str(e)}")
        # If there's an error, invalidate the cache
        await cache_delete(key)
