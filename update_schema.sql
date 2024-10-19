-- Update users table
ALTER TABLE users
ALTER COLUMN id TYPE uuid USING (gen_random_uuid());

-- Update user_chat_history table
ALTER TABLE user_chat_history
ALTER COLUMN user_id TYPE uuid USING (gen_random_uuid());

-- Update video_analysis_output table
ALTER TABLE video_analysis_output
ALTER COLUMN user_id TYPE uuid USING (gen_random_uuid());

-- Add a new UUID column to users table
ALTER TABLE users
ADD COLUMN new_id uuid DEFAULT gen_random_uuid();

-- Copy data from id to new_id
UPDATE users
SET new_id = id::uuid;

-- Drop the old id column
ALTER TABLE users
DROP COLUMN id;

-- Rename new_id to id
ALTER TABLE users
RENAME COLUMN new_id TO id;

-- Set id as the primary key
ALTER TABLE users
ADD PRIMARY KEY (id);

-- Update foreign key constraints
ALTER TABLE user_chat_history
ADD CONSTRAINT user_chat_history_user_id_fkey
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE video_analysis_output
ADD CONSTRAINT video_analysis_output_user_id_fkey
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
