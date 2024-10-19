import os
from supabase import create_client, Client
from typing import List, Dict, Optional

# Initialize Supabase client
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_ANON_KEY")
)

def create_user(username: str) -> Dict:
    response = supabase.table("users").insert({"username": username}).execute()
    return response.data[0] if response.data else {}

def get_user_by_username(username: str) -> Dict:
    response = supabase.table("users").select("*").eq("username", username).execute()
    return response.data[0] if response.data else {}

def insert_chat_message(user_id: str, message: str, chat_type: str = 'text') -> Dict:
    response = supabase.table("user_chat_history").insert({
        "user_id": user_id,
        "message": message,
        "chat_type": chat_type
    }).execute()
    return response.data[0] if response.data else {}

def get_chat_history(user_id: str, limit: int = 50) -> List[Dict]:
    response = supabase.table("user_chat_history").select("*").eq("user_id", user_id).order("TIMESTAMP", desc=True).limit(limit).execute()
    return response.data

def insert_video_analysis(user_id: str, upload_file_name: str, analysis: str, video_duration: Optional[str] = None, video_format: Optional[str] = None) -> Dict:
    response = supabase.table("video_analysis_output").insert({
        "user_id": user_id,
        "upload_file_name": upload_file_name,
        "analysis": analysis,
        "video_duration": video_duration,
        "video_format": video_format
    }).execute()
    return response.data[0] if response.data else {}

def get_video_analysis_history(user_id: str, limit: int = 10) -> List[Dict]:
    response = supabase.table("video_analysis_output").select("*").eq("user_id", user_id).order("TIMESTAMP", desc=True).limit(limit).execute()
    return response.data
