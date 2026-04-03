-- ============================================
-- 성능 인덱스 추가 (Nano 0.5GB 최적화)
-- Supabase SQL Editor에서 실행
-- ============================================

-- 1. trade_cache: 가장 큰 테이블, 매번 풀스캔 방지
CREATE INDEX IF NOT EXISTS idx_trade_cache_kapt_code
  ON trade_cache (kapt_code);

CREATE INDEX IF NOT EXISTS idx_trade_cache_year_month
  ON trade_cache (year_month);

-- 2. cards: agent_id로 항상 필터링 (RLS + 쿼리)
CREATE INDEX IF NOT EXISTS idx_cards_agent_id
  ON cards (agent_id);

CREATE INDEX IF NOT EXISTS idx_cards_trade_status
  ON cards (trade_status);

-- 3. apartments: 구 코드로 필터링
CREATE INDEX IF NOT EXISTS idx_apartments_lawd_cd
  ON apartments (lawd_cd);

-- 4. danji_pages: sitemap 생성 시 사용
CREATE INDEX IF NOT EXISTS idx_danji_pages_updated_at
  ON danji_pages (updated_at DESC);

-- 5. memos: agent_id로 조회
CREATE INDEX IF NOT EXISTS idx_memos_agent_id
  ON memos (agent_id);

-- 6. client_notes: agent_id로 조회
CREATE INDEX IF NOT EXISTS idx_client_notes_agent_id
  ON client_notes (agent_id);

-- 7. match_notifications: agent_id로 조회
CREATE INDEX IF NOT EXISTS idx_match_notifications_agent_id
  ON match_notifications (agent_id);

-- 확인
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
