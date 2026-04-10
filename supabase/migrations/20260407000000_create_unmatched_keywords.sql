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

-- RLS
ALTER TABLE public.unmatched_keywords ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own keywords"
  ON public.unmatched_keywords FOR SELECT
  USING (agent_id = auth.uid());

CREATE POLICY "Users can insert own keywords"
  ON public.unmatched_keywords FOR INSERT
  WITH CHECK (agent_id = auth.uid());

CREATE POLICY "Service role full access"
  ON public.unmatched_keywords FOR ALL
  USING (auth.role() = 'service_role');
