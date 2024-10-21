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
        "ALTER TABLE users ALTER COLUMN id TYPE uuid USING (id::uuid);",
        "ALTER TABLE user_chat_history ALTER COLUMN user_id TYPE uuid USING (user_id::uuid);",
        "ALTER TABLE video_analysis_output ALTER COLUMN user_id TYPE uuid USING (user_id::uuid);",
        "ALTER TABLE user_chat_history DROP CONSTRAINT IF EXISTS user_chat_history_user_id_fkey;",
        "ALTER TABLE user_chat_history ADD CONSTRAINT user_chat_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;",
        "ALTER TABLE video_analysis_output DROP CONSTRAINT IF EXISTS video_analysis_output_user_id_fkey;",
        "ALTER TABLE video_analysis_output ADD CONSTRAINT video_analysis_output_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;"
    ]

    for sql in schema_updates:
        try:
            response = supabase.postgrest.rpc('rpc_query', {'query': sql})
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
