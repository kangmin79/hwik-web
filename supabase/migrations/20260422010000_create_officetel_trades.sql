-- officetel_trades: 오피스텔 실거래 레코드 (매매/전세/월세)
-- 데이터 소스: 국토부 실거래가 공개시스템 (매매·전월세 API)
-- 적재 스크립트: officetel_test/load_trades_to_supabase.py
-- PK는 자동생성 + UNIQUE 복합키로 dedup

CREATE TABLE IF NOT EXISTS officetel_trades (
  id             bigserial PRIMARY KEY,
  officetel_id   text NOT NULL REFERENCES officetels(id) ON DELETE CASCADE,
  deal_type      text NOT NULL,               -- 매매 / 전세 / 월세
  deal_year      int  NOT NULL,
  deal_month     int  NOT NULL,
  deal_day       int  NOT NULL,
  price          int,                          -- 만원 (매매가 또는 보증금)
  monthly_rent   int  DEFAULT 0,               -- 월세 (매매/전세 시 0)
  excl_use_ar    double precision,             -- 전용면적 ㎡
  floor          int,

  UNIQUE (officetel_id, deal_type, deal_year, deal_month, deal_day, excl_use_ar, floor, price, monthly_rent)
);

CREATE INDEX IF NOT EXISTS idx_officetel_trades_lookup
  ON officetel_trades(officetel_id, deal_type, deal_year DESC, deal_month DESC, deal_day DESC);

CREATE INDEX IF NOT EXISTS idx_officetel_trades_year
  ON officetel_trades(deal_year DESC, deal_month DESC);
