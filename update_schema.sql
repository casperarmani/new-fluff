-- Update users table
ALTER TABLE users
ALTER COLUMN id TYPE uuid USING (id::uuid);

-- Update user_chat_history table
ALTER TABLE user_chat_history
ALTER COLUMN user_id TYPE uuid USING (user_id::uuid);

-- Update video_analysis_output table
ALTER TABLE video_analysis_output
ALTER COLUMN user_id TYPE uuid USING (user_id::uuid);

-- Update foreign key constraints
ALTER TABLE user_chat_history
DROP CONSTRAINT IF EXISTS user_chat_history_user_id_fkey,
ADD CONSTRAINT user_chat_history_user_id_fkey
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE video_analysis_output
DROP CONSTRAINT IF EXISTS video_analysis_output_user_id_fkey,
ADD CONSTRAINT video_analysis_output_user_id_fkey
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
