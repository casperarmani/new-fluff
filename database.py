import os
from supabase import create_client, Client
from typing import List, Dict, Optional
import uuid
import json
from redis_config import get_redis_client, CHAT_SESSION_TTL, DB_WRITE_BATCH_SIZE
import logging
import asyncio

# Initialize Supabase client
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_ANON_KEY")
)

# Initialize Redis client
redis_client = get_redis_client()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def write_messages_to_db(user_id: uuid.UUID, messages: List[Dict]):
    try:
        for message in messages:
            response = supabase.table("user_chat_history").insert(message).execute()
            if not response.data:
                logger.error(f"Failed to insert message for user {user_id}")
        logger.info(f"Wrote {len(messages)} messages to database for user {user_id}")
    except Exception as e:
        logger.error(f"Error writing messages to database: {str(e)}")

async def async_insert_chat_message(user_id: uuid.UUID, message: str, chat_type: str = 'text'):
    cache_key = f"chat_history:{user_id}"
    new_message = {
        "user_id": str(user_id),
        "message": message,
        "chat_type": chat_type,
        "timestamp": int(asyncio.get_event_loop().time())
    }

    try:
        # Update Redis cache
        cached_history = redis_client.get(cache_key)
        if cached_history:
            history = json.loads(cached_history)
            history.insert(0, new_message)
            redis_client.setex(cache_key, CHAT_SESSION_TTL, json.dumps(history[:50]))
        else:
            redis_client.setex(cache_key, CHAT_SESSION_TTL, json.dumps([new_message]))

        # Asynchronously write to database if batch size is reached
        cached_history = json.loads(redis_client.get(cache_key))
        if len(cached_history) >= DB_WRITE_BATCH_SIZE:
            asyncio.create_task(write_messages_to_db(user_id, cached_history))
            redis_client.delete(cache_key)

        return new_message
    except Exception as e:
        logger.error(f"Error inserting chat message: {str(e)}")
        return None

def get_chat_history(user_id: uuid.UUID, limit: int = 50) -> List[Dict]:
    cache_key = f"chat_history:{user_id}"
    
    # Try to get from Redis cache first
    try:
        cached_history = redis_client.get(cache_key)
        if cached_history:
            return json.loads(cached_history)[:limit]
    except Exception as e:
        logger.error(f"Error retrieving from Redis cache: {str(e)}")
    
    # If not in cache or error occurred, get from Supabase
    response = supabase.table("user_chat_history").select("*").eq("user_id", str(user_id)).order("COALESCE(timestamp, CURRENT_TIMESTAMP)", desc=True).limit(limit).execute()
    history = response.data
    
    # Update Redis cache
    try:
        redis_client.setex(cache_key, CHAT_SESSION_TTL, json.dumps(history))
    except Exception as e:
        logger.error(f"Error updating Redis cache: {str(e)}")
    
    return history

def create_user(email: str) -> Dict:
    response = supabase.table("users").insert({"email": email}).execute()
    return response.data[0] if response.data else {}

def get_user_by_email(email: str) -> Dict:
    response = supabase.table("users").select("*").eq("email", email).execute()
    return response.data[0] if response.data else {}

def check_user_exists(user_id: uuid.UUID) -> bool:
    response = supabase.table("users").select("id").eq("id", str(user_id)).execute()
    return len(response.data) > 0

def insert_video_analysis(user_id: uuid.UUID, upload_file_name: str, analysis: str, video_duration: Optional[str] = None, video_format: Optional[str] = None) -> Dict:
    response = supabase.table("video_analysis_output").insert({
        "user_id": str(user_id),
        "upload_file_name": upload_file_name,
        "analysis": analysis,
        "video_duration": video_duration,
        "video_format": video_format
    }).execute()
    return response.data[0] if response.data else {}

def get_video_analysis_history(user_id: uuid.UUID, limit: int = 10) -> List[Dict]:
    cache_key = f"video_analysis_history:{user_id}"
    
    # Try to get from Redis cache first
    try:
        cached_history = redis_client.get(cache_key)
        if cached_history:
            return json.loads(cached_history)[:limit]
    except Exception as e:
        logger.error(f"Error retrieving from Redis cache: {str(e)}")
    
    # If not in cache or error occurred, get from Supabase
    response = supabase.table("video_analysis_output").select("*").eq("user_id", str(user_id)).order("COALESCE(timestamp, CURRENT_TIMESTAMP)", desc=True).limit(limit).execute()
    history = response.data
    
    # Update Redis cache
    try:
        redis_client.setex(cache_key, CHAT_SESSION_TTL, json.dumps(history))
    except Exception as e:
        logger.error(f"Error updating Redis cache: {str(e)}")
    
    return history
