import os
from supabase import create_client, Client
from typing import List, Dict, Optional
import uuid
import json
from redis_config import get_redis_client
import logging

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
    
    # Insert into Supabase
    response = supabase.table("user_chat_history").insert({
        "user_id": str(user_id),
        "message": message,
        "chat_type": chat_type
    }).execute()
    
    # Update Redis cache
    if redis_client:
        try:
            cache_key = f"chat_history:{user_id}"
            cached_history = redis_client.get(cache_key)
            if cached_history:
                history = json.loads(cached_history)
                history.insert(0, response.data[0])  # Add new message at the beginning
                redis_client.setex(cache_key, 300, json.dumps(history[:50]))  # Keep only last 50 messages
            else:
                redis_client.setex(cache_key, 300, json.dumps([response.data[0]]))
        except Exception as e:
            logger.error(f"Error updating Redis cache: {str(e)}")
    
    return response.data[0] if response.data else {}

def get_chat_history(user_id: uuid.UUID, limit: int = 50) -> List[Dict]:
    cache_key = f"chat_history:{user_id}"
    
    # Try to get from Redis cache first
    if redis_client:
        try:
            cached_history = redis_client.get(cache_key)
            if cached_history:
                return json.loads(cached_history)[:limit]
        except Exception as e:
            logger.error(f"Error retrieving from Redis cache: {str(e)}")
    
    # If not in cache or error occurred, get from Supabase
    response = supabase.table("user_chat_history").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute()
    history = response.data
    
    # Update Redis cache
    if redis_client:
        try:
            redis_client.setex(cache_key, 300, json.dumps(history))
        except Exception as e:
            logger.error(f"Error updating Redis cache: {str(e)}")
    
    return history

def insert_video_analysis(user_id: uuid.UUID, upload_file_name: str, analysis: str, video_duration: Optional[str] = None, video_format: Optional[str] = None) -> Dict:
    # Insert into Supabase
    response = supabase.table("video_analysis_output").insert({
        "user_id": str(user_id),
        "upload_file_name": upload_file_name,
        "analysis": analysis,
        "video_duration": video_duration,
        "video_format": video_format
    }).execute()
    
    # Update Redis cache
    if redis_client:
        try:
            cache_key = f"video_analysis_history:{user_id}"
            cached_history = redis_client.get(cache_key)
            if cached_history:
                history = json.loads(cached_history)
                history.insert(0, response.data[0])  # Add new analysis at the beginning
                redis_client.setex(cache_key, 300, json.dumps(history[:10]))  # Keep only last 10 analyses
            else:
                redis_client.setex(cache_key, 300, json.dumps([response.data[0]]))
        except Exception as e:
            logger.error(f"Error updating Redis cache: {str(e)}")
    
    return response.data[0] if response.data else {}

def get_video_analysis_history(user_id: uuid.UUID, limit: int = 10) -> List[Dict]:
    cache_key = f"video_analysis_history:{user_id}"
    
    # Try to get from Redis cache first
    if redis_client:
        try:
            cached_history = redis_client.get(cache_key)
            if cached_history:
                return json.loads(cached_history)[:limit]
        except Exception as e:
            logger.error(f"Error retrieving from Redis cache: {str(e)}")
    
    # If not in cache or error occurred, get from Supabase
    response = supabase.table("video_analysis_output").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute()
    history = response.data
    
    # Update Redis cache
    if redis_client:
        try:
            redis_client.setex(cache_key, 300, json.dumps(history))
        except Exception as e:
            logger.error(f"Error updating Redis cache: {str(e)}")
    
    return history
