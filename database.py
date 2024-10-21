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
    
    # Write only to Supabase
    response = supabase.table("user_chat_history").insert(new_message).execute()
    logger.info(f"Chat message inserted into Supabase for user {user_id}")
    
    return response.data[0] if response.data else new_message

def get_chat_history(user_id: uuid.UUID, limit: int = 50) -> List[Dict]:
    # Fetch directly from Supabase
    start_time = time.time()
    response = supabase.table("user_chat_history").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute()
    history = response.data
    logger.info(f"Chat history retrieved from Supabase for user {user_id}")
    logger.info(f"Supabase get_chat_history time: {time.time() - start_time:.2f} seconds")
    
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
    
    # Write only to Supabase
    response = supabase.table("video_analysis_output").insert(new_analysis).execute()
    logger.info(f"Video analysis inserted into Supabase for user {user_id}")
    
    return response.data[0] if response.data else new_analysis

def get_video_analysis_history(user_id: uuid.UUID, limit: int = 10) -> List[Dict]:
    # Fetch directly from Supabase
    start_time = time.time()
    response = supabase.table("video_analysis_output").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute()
    history = response.data
    logger.info(f"Video analysis history retrieved from Supabase for user {user_id}")
    logger.info(f"Supabase get_video_analysis_history time: {time.time() - start_time:.2f} seconds")
    
    return history

def get_recent_chat_context(user_id: uuid.UUID, limit: int = 10) -> List[Dict]:
    cache_key = f"chat_context:{user_id}"
    if redis_client:
        try:
            context = redis_client.lrange(cache_key, 0, limit - 1)
            if context:
                return [json.loads(message) for message in context]
        except Exception as e:
            logger.error(f"Error retrieving chat context from Redis: {str(e)}")
    return []

def update_chat_context(user_id: uuid.UUID, message: Dict):
    cache_key = f"chat_context:{user_id}"
    if redis_client:
        try:
            redis_client.lpush(cache_key, json.dumps(message))
            redis_client.ltrim(cache_key, 0, 9)  # Keep only the last 10 messages
            logger.info(f"Chat context updated in Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating chat context in Redis: {str(e)}")

# Remove the update_session_context and get_session_context functions as they are no longer needed
