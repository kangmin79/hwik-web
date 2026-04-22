-- officetel_trades: 일일 증분 감지용 created_at 및 취소 플래그 추가
-- 매일 자동 워크플로우에서 "지난 24시간 내 신규/변경 레코드" 필터에 사용
-- is_canceled: 국토부 cdealType="O" (취소 거래) 처리용 soft-delete 플래그

ALTER TABLE officetel_trades
  ADD COLUMN IF NOT EXISTS created_at  timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS is_canceled boolean     DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_officetel_trades_created
  ON officetel_trades(created_at DESC);
