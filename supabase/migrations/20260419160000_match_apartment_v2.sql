-- match_apartment RPC v2
-- 변경:
--   1) similarity 계산 시 kapt_name/p_complex 양쪽에서 공백 + "아파트/오피스텔" suffix 제거 후 비교
--   2) sgg 힌트는 locate-card에서 가드 처리하므로 RPC는 기존 방식 유지 (있으면 필터)
-- 효과: "헬리오시티" vs "헬리오시티아파트" = 0.5 → 1.0 / "래미안대치팰리스" vs "래미안 대치 팰리스" = 0.33 → 1.0

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
DECLARE
  p_complex_norm text;
BEGIN
  -- 입력 단지명 정규화: 공백 제거 + "아파트/오피스텔" suffix 제거
  p_complex_norm := regexp_replace(replace(p_complex, ' ', ''), '아파트$|오피스텔$', '');

  RETURN QUERY
  WITH candidates AS (
    SELECT
      a.kapt_code,
      a.kapt_name,
      a.sgg,
      a.umd_nm,
      a.lat,
      a.lon,
      -- DB 단지명도 동일 정규화 후 비교
      similarity(
        regexp_replace(replace(a.kapt_name, ' ', ''), '아파트$|오피스텔$', ''),
        p_complex_norm
      )::float4 AS name_sim,
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
      -- 이름 필터: 정규화된 이름 유사도 0.15 이상 OR 정규화 부분 포함
      (
        similarity(
          regexp_replace(replace(a.kapt_name, ' ', ''), '아파트$|오피스텔$', ''),
          p_complex_norm
        ) > 0.15
        OR regexp_replace(replace(a.kapt_name, ' ', ''), '아파트$|오피스텔$', '') ILIKE '%' || p_complex_norm || '%'
      )
      AND (p_sgg IS NULL OR a.sgg LIKE '%' || p_sgg || '%')
      AND (p_umd IS NULL OR a.umd_nm LIKE '%' || p_umd || '%')
  )
  SELECT
    c.kapt_code, c.kapt_name, c.sgg, c.umd_nm, c.lat, c.lon,
    c.name_sim,
    c.dist_km,
    (c.name_sim * 60 +
     CASE
       WHEN c.dist_km IS NULL THEN 10
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
