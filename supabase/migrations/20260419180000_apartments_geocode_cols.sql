-- apartments 테이블에 카카오 geocode 좌표 저장 컬럼 추가
-- 배경: 중개사 주소(도로명/지번)로 정확 매칭 위해 apartments도 동일 geocode 좌표 저장
-- 기존 lat/lon은 K-apt 원본 좌표로 유지, doro_lat/lon·jibun_lat/lon은 카카오 geocode 결과

ALTER TABLE apartments
  ADD COLUMN IF NOT EXISTS doro_lat  double precision,
  ADD COLUMN IF NOT EXISTS doro_lon  double precision,
  ADD COLUMN IF NOT EXISTS jibun_lat double precision,
  ADD COLUMN IF NOT EXISTS jibun_lon double precision,
  ADD COLUMN IF NOT EXISTS geocode_status text,  -- 'ok' | 'doro_only' | 'jibun_only' | 'failed'
  ADD COLUMN IF NOT EXISTS geocode_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_apartments_doro_coord  ON apartments(doro_lat, doro_lon);
CREATE INDEX IF NOT EXISTS idx_apartments_jibun_coord ON apartments(jibun_lat, jibun_lon);
