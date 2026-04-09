-- 1. pg_trgm 확장 활성화 (유사도 검색)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. cards에 kapt_code 컬럼 추가
ALTER TABLE cards ADD COLUMN IF NOT EXISTS kapt_code text;

-- 3. 인덱스
CREATE INDEX IF NOT EXISTS idx_cards_kapt_code ON cards(kapt_code);
CREATE INDEX IF NOT EXISTS idx_apartments_name_trgm ON apartments USING gin(kapt_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_apartments_sgg ON apartments(sgg);

-- 4. 단지명 검색 RPC 함수: 이름 유사도 + 거리 기반 최적 매칭
CREATE OR REPLACE FUNCTION match_apartment(
  p_complex text,
  p_sgg text DEFAULT NULL,
  p_umd text DEFAULT NULL,
  p_lat float8 DEFAULT NULL,
  p_lng float8 DEFAULT NULL,
  p_radius_km float8 DEFAULT 5.0
)
RETURNS TABLE(
  kapt_code text,
  kapt_name text,
  sgg text,
  umd_nm text,
  lat float8,
  lon float8,
  name_similarity float4,
  distance_km float8,
  score float8
) LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  WITH candidates AS (
    SELECT
      a.kapt_code,
      a.kapt_name,
      a.sgg,
      a.umd_nm,
      a.lat,
      a.lon,
      similarity(a.kapt_name, p_complex)::float4 AS name_sim,
      CASE
        WHEN p_lat IS NOT NULL AND p_lng IS NOT NULL AND a.lat IS NOT NULL AND a.lon IS NOT NULL THEN
          6371 * acos(
            LEAST(1.0, GREATEST(-1.0,
              cos(radians(p_lat)) * cos(radians(a.lat)) *
              cos(radians(a.lon) - radians(p_lng)) +
              sin(radians(p_lat)) * sin(radians(a.lat))
            ))
          )
        ELSE NULL
      END AS dist_km
    FROM apartments a
    WHERE
      -- 이름 필터: 유사도 0.15 이상 OR 부분 포함
      (similarity(a.kapt_name, p_complex) > 0.15 OR a.kapt_name ILIKE '%' || p_complex || '%')
      -- 구 필터 (있으면)
      AND (p_sgg IS NULL OR a.sgg LIKE '%' || p_sgg || '%')
      -- 동 필터 (있으면)
      AND (p_umd IS NULL OR a.umd_nm LIKE '%' || p_umd || '%')
  )
  SELECT
    c.kapt_code, c.kapt_name, c.sgg, c.umd_nm, c.lat, c.lon,
    c.name_sim,
    c.dist_km,
    -- 종합 점수: 이름 유사도(0~1) * 60 + 거리 점수(0~40)
    (c.name_sim * 60 +
     CASE
       WHEN c.dist_km IS NULL THEN 10  -- 거리 정보 없으면 중간 점수
       WHEN c.dist_km <= 0.5 THEN 40
       WHEN c.dist_km <= 1.0 THEN 35
       WHEN c.dist_km <= 2.0 THEN 25
       WHEN c.dist_km <= 5.0 THEN 15
       WHEN c.dist_km <= 10.0 THEN 5
       ELSE 0
     END
    ) AS score
  FROM candidates c
  WHERE c.dist_km IS NULL OR c.dist_km <= p_radius_km
  ORDER BY score DESC
  LIMIT 5;
END;
$$;
