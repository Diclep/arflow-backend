-- ── Campo per errori di conversione backend — esegui su Supabase ───────────
ALTER TABLE models ADD COLUMN IF NOT EXISTS conversion_error TEXT;
