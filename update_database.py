import os
from supabase import create_client, Client

# Initialize Supabase client with service role key
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing from environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

def update_schema():
    schema_updates = [
        "ALTER TABLE user_chat_history ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE video_analysis_output ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
    ]

    for sql in schema_updates:
        try:
            response = supabase.rpc('execute_sql', {'query': sql}).execute()
            print(f"Executed SQL successfully: {sql}")
            print(f"Response: {response}")
        except Exception as e:
            print(f"Error executing SQL: {sql}")
            print(f"Error message: {str(e)}")
            return False
    return True

if __name__ == "__main__":
    print("Updating schema...")
    if update_schema():
        print("Schema updated successfully")
    else:
        print("Failed to update schema")
