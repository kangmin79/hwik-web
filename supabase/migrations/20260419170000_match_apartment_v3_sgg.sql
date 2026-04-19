-- match_apartment RPC v3: sgg 필터 완화
-- 배경: apartments.sgg 컬럼이 지역별 포맷 혼재
--   - 서울: "마포구"
--   - 경기 일부: "수원시" / "수원장안구" / "성남분당구" / "안양동안구"
--   - 일부: "성남시" (구 정보 없음)
-- 변경: sgg 매칭 조건을 양방향 부분 포함 + 접미사 제거 후 base 일치까지 확장
-- 주의: 이름 유사도 + 거리 가드로 False positive 방어하므로 sgg 느슨해도 안전

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
  p_sgg_base text;
BEGIN
  -- 단지명 정규화 (공백 + 아파트/오피스텔 suffix 제거)
  p_complex_norm := regexp_replace(replace(p_complex, ' ', ''), '아파트$|오피스텔$', '');
  -- sgg 베이스 (시/구/군 접미사 제거) — NULL 안전
  p_sgg_base := CASE WHEN p_sgg IS NULL THEN NULL ELSE regexp_replace(p_sgg, '(시|구|군)$', '') END;

  RETURN QUERY
  WITH candidates AS (
    SELECT
      a.kapt_code,
      a.kapt_name,
      a.sgg,
      a.umd_nm,
      a.lat,
      a.lon,
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
      (
        similarity(
          regexp_replace(replace(a.kapt_name, ' ', ''), '아파트$|오피스텔$', ''),
          p_complex_norm
        ) > 0.15
        OR regexp_replace(replace(a.kapt_name, ' ', ''), '아파트$|오피스텔$', '') ILIKE '%' || p_complex_norm || '%'
      )
      -- sgg 필터: 양방향 부분 포함 OR 접미사 제거 후 base 일치
      AND (
        p_sgg IS NULL
        OR a.sgg IS NULL
        OR a.sgg LIKE '%' || p_sgg || '%'
        OR p_sgg LIKE '%' || a.sgg || '%'
        OR regexp_replace(a.sgg, '(시|구|군)$', '') LIKE '%' || p_sgg_base || '%'
        OR p_sgg_base LIKE '%' || regexp_replace(a.sgg, '(시|구|군)$', '') || '%'
      )
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
