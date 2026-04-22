-- officetel_trades: 거래 유형 배지용 dealing_gbn 컬럼 추가
-- 국토부 매매 API 의 dealingGbn 필드 (중개거래 / 직거래)
-- 전월세는 해당 필드가 API 에서 제공되지 않음 (매매 전용)
-- backfill: officetel_test/backfill_dealing_gbn.py 로 117,325건 적재 완료

ALTER TABLE officetel_trades
  ADD COLUMN IF NOT EXISTS dealing_gbn text;

CREATE INDEX IF NOT EXISTS idx_officetel_trades_gbn
  ON officetel_trades(dealing_gbn) WHERE dealing_gbn IS NOT NULL;
