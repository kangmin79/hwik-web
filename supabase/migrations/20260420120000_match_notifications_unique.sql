-- match_notifications (agent_id, card_id, client_card_id) UNIQUE 제약 추가
-- 사유: auto-match가 ON CONFLICT upsert를 하는데 제약이 없어 400 에러 → 알림 저장 실패 누적
-- 2026-04-20

-- 1) 기존 중복 정리 (가장 최근 created_at만 유지)
DELETE FROM match_notifications a
USING match_notifications b
WHERE a.id < b.id
  AND a.agent_id = b.agent_id
  AND a.card_id = b.card_id
  AND a.client_card_id = b.client_card_id;

-- 2) UNIQUE 인덱스
CREATE UNIQUE INDEX IF NOT EXISTS match_notifications_agent_card_client_uq
  ON match_notifications (agent_id, card_id, client_card_id);
