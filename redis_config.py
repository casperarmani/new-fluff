import os
import redis
from redis.connection import ConnectionPool
import logging

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is not set")

# Create a connection pool
redis_pool = ConnectionPool.from_url(REDIS_URL, max_connections=10)

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

# Set TTL for chat sessions (e.g., 1 hour)
CHAT_SESSION_TTL = 3600

# Batch size for database writes
DB_WRITE_BATCH_SIZE = 10
