-- officetel_trade_raw: 국토부 API 원본 JSONB 영구 보존
-- 목적:
--   1. 집계/파생 테이블(officetels, officetel_trades)을 언제든 재구축 가능
--   2. API 응답 원본 보존으로 디버깅/감사 추적성 확보
--   3. 2026-04-23 사고처럼 집계 버그 발생해도 원본이 남아있음

CREATE TABLE IF NOT EXISTS officetel_trade_raw (
  id              bigserial PRIMARY KEY,
  api_source      text NOT NULL,                          -- 'trade_sale' | 'trade_rent' | 'bldg_recap' | 'bldg_title'
  sync_run_id     text NOT NULL,                          -- e.g. '20260424_initial_5y'
  sigungu_cd      text,                                   -- 5자리 시군구 코드
  deal_ym         text,                                   -- YYYYMM (거래 API만)
  apt_seq         text,                                   -- 단지 식별자 (거래 API)
  mgm_bldrgst_pk  text,                                   -- 관리번호 (건축물대장)
  -- 식별 핵심 필드 (dedup 키)
  deal_ymd        text,                                   -- YYYYMMDD
  price_signature text,                                   -- 정규화된 가격+면적+층 해시
  fetched_at      timestamptz NOT NULL DEFAULT now(),
  data            jsonb NOT NULL,                         -- API 응답 원본

  -- 멱등성: 식별 핵심 필드로 dedup (data 전체 포함 금지 — 필드 한 개 변하면 부풀어 오름)
  UNIQUE (api_source, apt_seq, mgm_bldrgst_pk, deal_ymd, price_signature)
);

CREATE INDEX IF NOT EXISTS idx_trade_raw_source_run
  ON officetel_trade_raw(api_source, sync_run_id);
CREATE INDEX IF NOT EXISTS idx_trade_raw_apt_seq
  ON officetel_trade_raw(apt_seq) WHERE apt_seq IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trade_raw_mgm
  ON officetel_trade_raw(mgm_bldrgst_pk) WHERE mgm_bldrgst_pk IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trade_raw_fetched
  ON officetel_trade_raw(fetched_at DESC);

COMMENT ON TABLE officetel_trade_raw IS
  '국토부 API 원본 JSONB. 영구 보존, CASCADE 없음, 집계/파생은 이 테이블에서 재계산.';
