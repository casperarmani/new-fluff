import os
import logging
from supabase import create_client, Client
from typing import List, Dict, Optional
import uuid
from redis_config import get_redis_client, CHAT_SESSION_TTL, cache_get, cache_set, write_through_cache
import json
import asyncio
from datetime import datetime, timezone

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_ANON_KEY")
)

# Initialize Redis client
redis_client = get_redis_client()

def create_user(email: str) -> Dict:
    try:
        response = supabase.table("users").insert({"email": email}).execute()
        logger.info(f"Successfully created user with email: {email}")
        return response.data[0] if response.data else {}
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise

def get_user_by_email(email: str) -> Dict:
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        logger.error(f"Error getting user by email: {str(e)}")
        raise

def check_user_exists(user_id: uuid.UUID) -> bool:
    try:
        response = supabase.table("users").select("id").eq("id", str(user_id)).execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Error checking if user exists: {str(e)}")
        raise

async def async_insert_chat_message(user_id: uuid.UUID, message: str, chat_type: str = 'text') -> Dict:
    user_exists = check_user_exists(user_id)
    if not user_exists:
        raise ValueError(f"User with id {user_id} does not exist")
    try:
        new_message = {
            "user_id": str(user_id),
            "message": message,
            "chat_type": chat_type,
            "TIMESTAMP": datetime.now(timezone.utc).isoformat()
        }
        
        cache_key = f"chat_history:{user_id}"
        
        async def db_write_func(value):
            return await asyncio.to_thread(
                supabase.table("user_chat_history").insert(value).execute
            )
        
        # Use write-through cache
        await write_through_cache(cache_key, new_message, db_write_func)
        
        logger.info(f"Successfully inserted chat message for user {user_id}")
        return new_message
    except Exception as e:
        logger.error(f"Error inserting chat message: {str(e)}")
        raise

async def get_chat_history(user_id: uuid.UUID, limit: int = 50) -> List[Dict]:
    try:
        cache_key = f"chat_history:{user_id}"
        cached_history = await cache_get(cache_key)
        if cached_history:
            logger.info(f"Retrieved chat history for user {user_id} from Redis cache")
            return cached_history[:limit]
        
        response = await asyncio.to_thread(
            supabase.table("user_chat_history").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute
        )
        history = response.data
        
        # Update Redis cache
        await cache_set(cache_key, json.dumps(history), CHAT_SESSION_TTL)
        
        logger.info(f"Retrieved chat history for user {user_id} from database")
        return history
    except Exception as e:
        logger.error(f"Error getting chat history: {str(e)}")
        raise

async def insert_video_analysis(user_id: uuid.UUID, upload_file_name: str, analysis: str, video_duration: Optional[str] = None, video_format: Optional[str] = None) -> Dict:
    try:
        new_analysis = {
            "user_id": str(user_id),
            "upload_file_name": upload_file_name,
            "analysis": analysis,
            "video_duration": video_duration,
            "video_format": video_format,
            "TIMESTAMP": datetime.now(timezone.utc).isoformat()
        }
        
        cache_key = f"video_analysis_history:{user_id}"
        
        async def db_write_func(value):
            return await asyncio.to_thread(
                supabase.table("video_analysis_output").insert(value).execute
            )
        
        # Use write-through cache
        await write_through_cache(cache_key, new_analysis, db_write_func)
        
        logger.info(f"Successfully inserted video analysis for user {user_id}")
        return new_analysis
    except Exception as e:
        logger.error(f"Error inserting video analysis: {str(e)}")
        raise

async def get_video_analysis_history(user_id: uuid.UUID, limit: int = 10) -> List[Dict]:
    try:
        cache_key = f"video_analysis_history:{user_id}"
        cached_history = await cache_get(cache_key)
        if cached_history:
            logger.info(f"Retrieved video analysis history for user {user_id} from Redis cache")
            return cached_history[:limit]
        
        response = await asyncio.to_thread(
            supabase.table("video_analysis_output").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute
        )
        history = response.data
        
        # Update Redis cache
        await cache_set(cache_key, json.dumps(history), CHAT_SESSION_TTL)
        
        logger.info(f"Retrieved video analysis history for user {user_id} from database")
        return history
    except Exception as e:
        logger.error(f"Error getting video analysis history: {str(e)}")
        raise
