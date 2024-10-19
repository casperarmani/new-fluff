-- Update users table
ALTER TABLE users
ALTER COLUMN id TYPE uuid USING (gen_random_uuid());

-- Update user_chat_history table
ALTER TABLE user_chat_history
ALTER COLUMN user_id TYPE uuid USING (gen_random_uuid());

-- Update video_analysis_output table
ALTER TABLE video_analysis_output
ALTER COLUMN user_id TYPE uuid USING (gen_random_uuid());
