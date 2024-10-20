import os
from supabase import create_client, Client

# Initialize Supabase client with service role key
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing from environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

def create_execute_sql_function():
    sql = """
    CREATE OR REPLACE FUNCTION public.execute_sql(query text)
    RETURNS void AS $$
    BEGIN
      EXECUTE query;
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER;

    GRANT EXECUTE ON FUNCTION public.execute_sql(text) TO authenticated;
    """
    
    try:
        response = supabase.rpc('postgres', {'query': sql}).execute()
        print("Execute SQL function created successfully.")
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"Error creating execute_sql function: {str(e)}")
        return False

if __name__ == "__main__":
    if create_execute_sql_function():
        print("Function creation successful.")
    else:
        print("Function creation failed.")
