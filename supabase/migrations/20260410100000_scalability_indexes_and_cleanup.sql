-- ============================================================
-- 확장성 대비 (Scalability preparations)
-- 2026-04-10: 중개사 수 증가 대비 사전 최적화
-- ============================================================

-- 1. cards.embedding 벡터 검색 인덱스 (있으면 스킵)
-- ivfflat: 10k 이하에서 빠름, 100k 이상이면 hnsw 권장
-- cosine 유사도 (vector_cosine_ops)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'cards'
      AND indexname = 'cards_embedding_ivfflat_idx'
  ) THEN
    -- lists = sqrt(N) 정도가 적당 (현재 ~5000 카드 → lists=70)
    CREATE INDEX cards_embedding_ivfflat_idx
      ON public.cards
      USING ivfflat (embedding vector_cosine_ops)
      WITH (lists = 100);
  END IF;
END $$;

-- 2. 자주 쓰는 필터 컬럼 인덱스 (중개사 매물 조회 빠르게)
CREATE INDEX IF NOT EXISTS cards_agent_id_idx
  ON public.cards (agent_id);

CREATE INDEX IF NOT EXISTS cards_agent_type_created_idx
  ON public.cards (agent_id, created_at DESC)
  WHERE trade_status != '완료';

-- 3. match_notifications 인덱스 (브리핑 조회 빠르게)
CREATE INDEX IF NOT EXISTS match_notifications_agent_unread_idx
  ON public.match_notifications (agent_id, is_read, created_at DESC)
  WHERE is_read = false;

-- 4. client_notes 인덱스 (일정 조회 빠르게)
CREATE INDEX IF NOT EXISTS client_notes_agent_alert_idx
  ON public.client_notes (agent_id, alert_done, alert_date)
  WHERE alert_done = false AND alert_date IS NOT NULL;

-- ============================================================
-- 5. 오래된 match_notifications 자동 삭제 함수
-- ============================================================
-- 30일 이상 지난 알림 삭제 — 테이블 무한 증가 방지
CREATE OR REPLACE FUNCTION cleanup_old_match_notifications()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  deleted_count integer;
BEGIN
  DELETE FROM public.match_notifications
  WHERE created_at < NOW() - INTERVAL '30 days';

  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END $$;

COMMENT ON FUNCTION cleanup_old_match_notifications IS
  '30일 이상 지난 match_notifications 삭제 (cron으로 매일 실행)';

-- ============================================================
-- 6. pg_cron으로 매일 새벽 3시에 cleanup 실행
-- ============================================================
-- pg_cron 익스텐션 활성화 (Supabase는 이미 enabled)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 기존 스케줄 제거 (idempotent)
DO $$
BEGIN
  PERFORM cron.unschedule('cleanup-old-match-notifications');
EXCEPTION WHEN OTHERS THEN
  NULL; -- 없으면 무시
END $$;

-- 매일 새벽 3시 (KST 12시) 실행
SELECT cron.schedule(
  'cleanup-old-match-notifications',
  '0 3 * * *',
  $$SELECT cleanup_old_match_notifications();$$
);
