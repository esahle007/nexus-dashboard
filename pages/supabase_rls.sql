-- ============================================================
-- Project Nexus — Row Level Security
-- Run this in Supabase SQL Editor
-- Ensures each user only sees their own data
-- ============================================================

-- Enable RLS on food_log
ALTER TABLE food_log ENABLE ROW LEVEL SECURITY;

-- Policy: users can only read their own rows
CREATE POLICY "Users read own food logs"
ON food_log FOR SELECT
USING (auth.uid()::text = user_id);

-- Policy: users can only insert their own rows
CREATE POLICY "Users insert own food logs"
ON food_log FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

-- Policy: users can only update their own rows
CREATE POLICY "Users update own food logs"
ON food_log FOR UPDATE
USING (auth.uid()::text = user_id);

-- Policy: users can only delete their own rows
CREATE POLICY "Users delete own food logs"
ON food_log FOR DELETE
USING (auth.uid()::text = user_id);

-- ── Verify RLS is active ──────────────────────────────────────
SELECT tablename, rowsecurity
FROM pg_tables
WHERE tablename = 'food_log';
-- Should show rowsecurity = true
