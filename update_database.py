import os
from supabase import create_client, Client
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase client with service role key
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing from environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

def update_schema():
    schema_updates = [
        "ALTER TABLE user_chat_history ADD COLUMN IF NOT EXISTS \"TIMESTAMP\" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE video_analysis_output ADD COLUMN IF NOT EXISTS \"TIMESTAMP\" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE user_chat_history ALTER COLUMN \"TIMESTAMP\" SET DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE video_analysis_output ALTER COLUMN \"TIMESTAMP\" SET DEFAULT CURRENT_TIMESTAMP;",
    ]

    for sql in schema_updates:
        try:
            response = supabase.postgres.sql(sql)
            logger.info(f"Executed SQL successfully: {sql}")
            logger.info(f"Response: {response}")
        except Exception as e:
            logger.error(f"Error executing SQL: {sql}")
            logger.error(f"Error message: {str(e)}")
            return False
    return True

if __name__ == "__main__":
    logger.info("Updating schema...")
    if update_schema():
        logger.info("Schema updated successfully")
    else:
        logger.error("Failed to update schema")
