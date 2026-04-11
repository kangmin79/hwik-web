-- ============================================================
-- 개인 일정 지원: client_notes.client_card_id NULL 허용
-- 2026-04-11: 달력에서 "추가" 버튼으로 손님 없는 개인 일정 저장
-- ============================================================

ALTER TABLE public.client_notes
  ALTER COLUMN client_card_id DROP NOT NULL;

COMMENT ON COLUMN public.client_notes.client_card_id IS
  'NULL이면 개인 일정 (세무서 방문 등 손님 무관)';
