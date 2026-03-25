-- match_properties_for_client: 손님 카드의 임베딩으로 매물 벡터 검색
-- Supabase SQL Editor에서 실행하세요.
-- 이 함수가 없어도 match-properties Edge Function은 search_cards_advanced 폴백으로 동작합니다.

CREATE OR REPLACE FUNCTION match_properties_for_client(
  p_client_embedding vector(1536),
  p_agent_id uuid,
  p_trade_type text DEFAULT NULL,
  p_threshold float DEFAULT 0.3,
  p_limit int DEFAULT 20
)
RETURNS TABLE (
  id uuid,
  property jsonb,
  agent_comment text,
  price_number numeric,
  trade_status text,
  photos text[],
  lat float,
  lng float,
  created_at timestamptz,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    c.id,
    c.property,
    c.agent_comment,
    c.price_number,
    c.trade_status,
    c.photos,
    c.lat::float,
    c.lng::float,
    c.created_at,
    (1 - (c.embedding <=> p_client_embedding))::float AS similarity
  FROM cards c
  WHERE c.embedding IS NOT NULL
    AND c.property->>'type' IN ('매매', '전세', '월세')
    AND c.agent_id = p_agent_id
    AND (p_trade_type IS NULL OR c.property->>'type' = p_trade_type)
    AND (1 - (c.embedding <=> p_client_embedding)) >= p_threshold
  ORDER BY c.embedding <=> p_client_embedding
  LIMIT p_limit;
END;
$$;
