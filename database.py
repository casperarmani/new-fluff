import os
from supabase import create_client, Client
from typing import List, Dict, Optional
import uuid

# Initialize Supabase client
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_ANON_KEY")
)

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
    response = supabase.table("user_chat_history").insert({
        "user_id": str(user_id),
        "message": message,
        "chat_type": chat_type
    }).execute()
    return response.data[0] if response.data else {}

def get_chat_history(user_id: uuid.UUID, limit: int = 50) -> List[Dict]:
    response = supabase.table("user_chat_history").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute()
    return response.data

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
    response = supabase.table("video_analysis_output").select("*").eq("user_id", str(user_id)).order("TIMESTAMP", desc=True).limit(limit).execute()
    return response.data
