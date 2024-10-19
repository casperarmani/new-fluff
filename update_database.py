import os
from supabase.client import create_client, Client

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing from environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

def update_schema():
    with open("update_schema.sql", "r") as f:
        sql = f.read()
    
    try:
        result = supabase.rpc("execute_sql", {"query": sql}).execute()
        print("Update schema result:", result)
        return True
    except Exception as e:
        print("Error updating schema:", str(e))
        return False

if __name__ == "__main__":
    success = update_schema()
    if success:
        print("Schema updated successfully")
    else:
        print("Failed to update schema")
