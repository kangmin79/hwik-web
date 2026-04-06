CREATE TABLE IF NOT EXISTS unmatched_keywords (
  id bigserial PRIMARY KEY,
  keyword text NOT NULL,
  source text DEFAULT 'feature',
  agent_id uuid,
  card_id text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_unmatched_kw ON unmatched_keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_unmatched_created ON unmatched_keywords(created_at);
