-- AI 자가진화 태그 매핑 테이블
-- 키워드로 못 잡은 표현 → AI가 분석 → 다음부터 키워드로 잡힘
CREATE TABLE IF NOT EXISTS ai_tag_mappings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_text text NOT NULL,          -- "24시간 관리 가능한", "살기 좋은 동네"
  standard_tag text NOT NULL,        -- "보안", "조용한동네"
  confidence float DEFAULT 0.8,      -- AI 확신도 (0~1)
  use_count int DEFAULT 1,           -- 이 매핑이 사용된 횟수
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- unique: 같은 input → 같은 tag는 하나만
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_tag_unique ON ai_tag_mappings(input_text, standard_tag);
-- 인덱스: input_text로 빠른 조회
CREATE INDEX IF NOT EXISTS idx_ai_tag_input ON ai_tag_mappings(input_text);
-- 인덱스: confidence 높은 것 우선
CREATE INDEX IF NOT EXISTS idx_ai_tag_confidence ON ai_tag_mappings(confidence DESC);

-- RLS: 모든 Edge Function에서 읽기 가능
ALTER TABLE ai_tag_mappings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "ai_tag_mappings_read" ON ai_tag_mappings FOR SELECT USING (true);
CREATE POLICY "ai_tag_mappings_insert" ON ai_tag_mappings FOR INSERT WITH CHECK (true);
CREATE POLICY "ai_tag_mappings_update" ON ai_tag_mappings FOR UPDATE USING (true);
