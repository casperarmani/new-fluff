import os
from supabase import create_client, Client
from typing import List, Dict, Optional
import uuid
import json
from redis_config import get_redis_client
import logging
import time

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

def create_user(email: str) -> Dict:
    response = supabase.table("users").insert({"email": email}).execute()
    return response.data[0] if response.data else {}

def get_user_by_email(email: str) -> Dict:
    response = supabase.table("users").select("*").eq("email", email).execute()
    return response.data[0] if response.data else {}

def check_user_exists(user_id: uuid.UUID) -> bool:
    response = supabase.table("users").select("id").eq("id", str(user_id)).execute()
    return len(response.data) > 0

def insert_chat_message(user_id: uuid.UUID, message: str, chat_type: str = 'text') -> Dict:
    user_exists = check_user_exists(user_id)
    if not user_exists:
        raise ValueError(f"User with id {user_id} does not exist")
    
    new_message = {
        "user_id": str(user_id),
        "message": message,
        "chat_type": chat_type,
        "TIMESTAMP": time.time()
    }
    
    # Write to Redis first (Write-through caching)
    if redis_client:
        try:
            cache_key = f"chat_history:{user_id}"
            cached_history = redis_client.get(cache_key)
            if cached_history:
                history = json.loads(cached_history)
                history.insert(0, new_message)
                redis_client.setex(cache_key, 3600, json.dumps(history[:50]))  # Cache for 1 hour
            else:
                redis_client.setex(cache_key, 3600, json.dumps([new_message]))
            logger.info(f"Chat message cached for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating Redis cache: {str(e)}")
    
    # Then write to Supabase
    response = supabase.table("user_chat_history").insert(new_message).execute()
    logger.info(f"Chat message inserted into Supabase for user {user_id}")
    
    return response.data[0] if response.data else new_message

def get_chat_history(user_id: uuid.UUID, limit: int = 50) -> List[Dict]:
    cache_key = f"chat_history:{user_id}"
    
    # Try to get from Redis cache first
    if redis_client:
        try:
            start_time = time.time()
            cached_history = redis_client.get(cache_key)
            if cached_history:
                history = json.loads(cached_history)[:limit]
                logger.info(f"Chat history retrieved from Redis cache for user {user_id}")
                logger.info(f"Redis get_chat_history time: {time.time() - start_time:.2f} seconds")
                return history
        except Exception as e:
            logger.error(f"Error retrieving from Redis cache: {str(e)}")
    
    # If not in cache or error occurred, get from Supabase
    start_time = time.time()
    response = supabase.table("user_chat_history").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute()
    history = response.data
    logger.info(f"Chat history retrieved from Supabase for user {user_id}")
    logger.info(f"Supabase get_chat_history time: {time.time() - start_time:.2f} seconds")
    
    # Update Redis cache
    if redis_client:
        try:
            redis_client.setex(cache_key, 3600, json.dumps(history))  # Cache for 1 hour
            logger.info(f"Chat history cached in Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating Redis cache: {str(e)}")
    
    return history

def insert_video_analysis(user_id: uuid.UUID, upload_file_name: str, analysis: str, video_duration: Optional[str] = None, video_format: Optional[str] = None) -> Dict:
    new_analysis = {
        "user_id": str(user_id),
        "upload_file_name": upload_file_name,
        "analysis": analysis,
        "video_duration": video_duration,
        "video_format": video_format,
        "TIMESTAMP": time.time()
    }
    
    # Write to Redis first (Write-through caching)
    if redis_client:
        try:
            cache_key = f"video_analysis_history:{user_id}"
            cached_history = redis_client.get(cache_key)
            if cached_history:
                history = json.loads(cached_history)
                history.insert(0, new_analysis)
                redis_client.setex(cache_key, 3600, json.dumps(history[:10]))  # Cache for 1 hour
            else:
                redis_client.setex(cache_key, 3600, json.dumps([new_analysis]))
            logger.info(f"Video analysis cached for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating Redis cache: {str(e)}")
    
    # Then write to Supabase
    response = supabase.table("video_analysis_output").insert(new_analysis).execute()
    logger.info(f"Video analysis inserted into Supabase for user {user_id}")
    
    return response.data[0] if response.data else new_analysis

def get_video_analysis_history(user_id: uuid.UUID, limit: int = 10) -> List[Dict]:
    cache_key = f"video_analysis_history:{user_id}"
    
    # Try to get from Redis cache first
    if redis_client:
        try:
            start_time = time.time()
            cached_history = redis_client.get(cache_key)
            if cached_history:
                history = json.loads(cached_history)[:limit]
                logger.info(f"Video analysis history retrieved from Redis cache for user {user_id}")
                logger.info(f"Redis get_video_analysis_history time: {time.time() - start_time:.2f} seconds")
                return history
        except Exception as e:
            logger.error(f"Error retrieving from Redis cache: {str(e)}")
    
    # If not in cache or error occurred, get from Supabase
    start_time = time.time()
    response = supabase.table("video_analysis_output").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute()
    history = response.data
    logger.info(f"Video analysis history retrieved from Supabase for user {user_id}")
    logger.info(f"Supabase get_video_analysis_history time: {time.time() - start_time:.2f} seconds")
    
    # Update Redis cache
    if redis_client:
        try:
            redis_client.setex(cache_key, 3600, json.dumps(history))  # Cache for 1 hour
            logger.info(f"Video analysis history cached in Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating Redis cache: {str(e)}")
    
    return history

def update_session_context(user_id: uuid.UUID, context: Dict):
    cache_key = f"session_context:{user_id}"
    if redis_client:
        try:
            redis_client.setex(cache_key, 3600, json.dumps(context))  # Set expiration to 1 hour
            logger.info(f"Session context updated in Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating session context in Redis: {str(e)}")

def get_session_context(user_id: uuid.UUID) -> Dict:
    cache_key = f"session_context:{user_id}"
    if redis_client:
        try:
            context = redis_client.get(cache_key)
            if context:
                logger.info(f"Session context retrieved from Redis for user {user_id}")
                return json.loads(context)
        except Exception as e:
            logger.error(f"Error retrieving session context from Redis: {str(e)}")
    return {}
