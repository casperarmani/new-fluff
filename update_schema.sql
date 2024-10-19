-- Update user_chat_history table
ALTER TABLE user_chat_history
ALTER COLUMN user_id TYPE text;

-- Update video_analysis_output table
ALTER TABLE video_analysis_output
ALTER COLUMN user_id TYPE text;
