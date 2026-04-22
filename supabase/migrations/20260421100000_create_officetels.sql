-- officetels: 오피스텔 단지 마스터 (apartments와 대칭)
-- 생성 배경: 매물 등록 시 오피스텔 단지 자동 매칭용 마스터 데이터
-- 데이터 소스: officetel_test/ 파이프라인 (국토부 실거래 + 건축물대장 + 카카오 geocode)
-- ID 규칙: 'o' + sha256(mgmBldrgstPk)[:7자리숫자] = 8자 고정 (아파트 a{숫자}와 대칭)

CREATE TABLE IF NOT EXISTS officetels (
  id                  text PRIMARY KEY,              -- o0336018
  mgm_bldrgst_pk      text UNIQUE,                    -- 건축물대장 관리번호 (재동기화 안전장치)

  -- 주소
  sido                text,                           -- 서울특별시
  sgg                 text,                           -- 중랑구
  umd                 text,                           -- 망우동
  jibun               text,                           -- 584
  bjdong_cd           text,                           -- 10500 (법정동 코드 5자리)

  -- 이름
  final_display_name  text,                           -- UI 표시용 단지명 (정제된 이름)
  bld_nm              text,                           -- 건축물대장 원본 건물명

  -- 좌표 2쌍 (apartments의 doro_lat/lon, jibun_lat/lon과 동일 철학)
  jibun_addr          text,
  jibun_lat           double precision,
  jibun_lng           double precision,
  road_addr           text,
  road_lat            double precision,
  road_lng            double precision,
  coord_diff_m        real,                           -- 지번/도로명 좌표 차이 (m)

  -- 건축물 속성
  main_purps          text,                           -- 주용도 (업무시설 등)
  build_year          int,
  use_apr_day         text,                           -- 사용승인일 YYYYMMDD
  tot_area            double precision,               -- 연면적 ㎡
  arch_area           double precision,               -- 건축면적 ㎡
  grnd_flr            int,                            -- 지상층수
  ugrnd_flr           int,                            -- 지하층수
  hhld_cnt            int,                            -- 세대수/호수

  -- 실거래/면적 집계
  trade_count         int,                            -- 최근 5년 실거래 건수
  excl_area_min       double precision,               -- 전용면적 최소 ㎡
  excl_area_max       double precision,               -- 전용면적 최대 ㎡

  -- URL
  url                 text,                           -- /officetel/서울-중랑-...-o0336018
  slug                text,                           -- url에서 도메인/prefix 제거한 슬러그

  property_type       text DEFAULT 'offi',            -- apartments와 대칭 (apt vs offi)

  -- SEO 페이지 노출 여부 (B정책: 5년 거래 3건 미만 단지는 false — 저품질 방지)
  -- false여도 DB엔 저장 (매물 등록 매칭용)
  seo_eligible        boolean DEFAULT true,

  created_at          timestamptz DEFAULT now(),
  updated_at          timestamptz DEFAULT now()
);

-- 인덱스: 매칭/검색용
CREATE INDEX IF NOT EXISTS idx_officetels_sgg          ON officetels(sgg);
CREATE INDEX IF NOT EXISTS idx_officetels_umd          ON officetels(umd);
CREATE INDEX IF NOT EXISTS idx_officetels_bjdong_cd    ON officetels(bjdong_cd);
CREATE INDEX IF NOT EXISTS idx_officetels_jibun_coord  ON officetels(jibun_lat, jibun_lng);
CREATE INDEX IF NOT EXISTS idx_officetels_road_coord   ON officetels(road_lat, road_lng);
CREATE INDEX IF NOT EXISTS idx_officetels_name_trgm    ON officetels USING gin(final_display_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_officetels_seo_eligible ON officetels(seo_eligible) WHERE seo_eligible = true;


-- officetel_pyeongs: 평형별 면적 엔트리 (apartments.pyeongs jsonb와 달리 별도 테이블)
-- 이유: (1) 정규화 용이 (2) 쿼리 성능 (3) 매물 등록 시 특정 평형 매칭
CREATE TABLE IF NOT EXISTS officetel_pyeongs (
  officetel_id        text NOT NULL REFERENCES officetels(id) ON DELETE CASCADE,
  exclu               double precision NOT NULL,      -- 전용면적 ㎡
  supply_residential  double precision,               -- 공급면적 (주거공용 기준) — 메인 노출
  supply_contract     double precision,               -- 계약면적 (지하주차장 포함) — 보조
  ho_count            int,                            -- 해당 평형 호수
  PRIMARY KEY (officetel_id, exclu)
);

CREATE INDEX IF NOT EXISTS idx_officetel_pyeongs_exclu ON officetel_pyeongs(exclu);
