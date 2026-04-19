-- 이름+지역 기반 단지 매칭 RPC (Waterfall Step 3 전용)
-- 주소(도로명/지번) 없거나 좌표 매칭 실패 시 fallback
-- 조건: sgg(양방향 base) + umd_nm + kapt_name 정규화 후 정확 포함
-- False positive 방지: 결과 1개만 허용 (호출 측에서 처리), 공식 A코드 우선

CREATE OR REPLACE FUNCTION match_apartment_by_name_region(
  p_complex text,
  p_sgg text,
  p_umd text,
  p_lat float8 DEFAULT NULL,
  p_lng float8 DEFAULT NULL
)
RETURNS TABLE(
  kapt_code text,
  kapt_name text,
  sgg text,
  umd_nm text,
  doro_juso text,
  property_type text,
  target_lat float8,
  target_lon float8,
  distance_km float8
) LANGUAGE plpgsql AS $$
DECLARE
  p_complex_norm text;
  p_sgg_base text;
BEGIN
  -- 정규화
  p_complex_norm := regexp_replace(replace(p_complex, ' ', ''), '아파트$|오피스텔$', '');
  p_sgg_base := CASE WHEN p_sgg IS NULL THEN NULL ELSE regexp_replace(p_sgg, '(시|구|군)$', '') END;

  RETURN QUERY
  SELECT
    a.kapt_code,
    a.kapt_name,
    a.sgg,
    a.umd_nm,
    a.doro_juso,
    a.property_type,
    COALESCE(a.doro_lat, a.jibun_lat, a.lat) AS target_lat,
    COALESCE(a.doro_lon, a.jibun_lon, a.lon) AS target_lon,
    CASE
      WHEN p_lat IS NOT NULL AND p_lng IS NOT NULL
        AND COALESCE(a.doro_lat, a.jibun_lat, a.lat) IS NOT NULL
        AND COALESCE(a.doro_lon, a.jibun_lon, a.lon) IS NOT NULL THEN
        6371 * acos(
          LEAST(1.0, GREATEST(-1.0,
            cos(radians(p_lat)) * cos(radians(COALESCE(a.doro_lat, a.jibun_lat, a.lat))) *
            cos(radians(COALESCE(a.doro_lon, a.jibun_lon, a.lon)) - radians(p_lng)) +
            sin(radians(p_lat)) * sin(radians(COALESCE(a.doro_lat, a.jibun_lat, a.lat)))
          ))
        )
      ELSE NULL
    END AS distance_km
  FROM apartments a
  WHERE
    -- 단지명 정규화 후 부분 포함 (핵심: 3자 이상 토큰 겹침)
    (
      regexp_replace(replace(a.kapt_name, ' ', ''), '아파트$|오피스텔$', '') ILIKE '%' || p_complex_norm || '%'
      OR p_complex_norm ILIKE '%' || regexp_replace(replace(a.kapt_name, ' ', ''), '아파트$|오피스텔$', '') || '%'
    )
    -- sgg 매칭: 양방향 + base
    AND p_sgg IS NOT NULL
    AND a.sgg IS NOT NULL
    AND (
      a.sgg LIKE '%' || p_sgg || '%'
      OR p_sgg LIKE '%' || a.sgg || '%'
      OR regexp_replace(a.sgg, '(시|구|군)$', '') LIKE '%' || p_sgg_base || '%'
      OR p_sgg_base LIKE '%' || regexp_replace(a.sgg, '(시|구|군)$', '') || '%'
    )
    -- umd 필수
    AND p_umd IS NOT NULL
    AND a.umd_nm IS NOT NULL
    AND a.umd_nm LIKE '%' || p_umd || '%'
  ORDER BY
    -- 공식 A코드 우선
    CASE WHEN a.kapt_code ~ '^A\d' THEN 0 ELSE 1 END,
    -- 좌표 있으면 가까운 순
    CASE
      WHEN p_lat IS NOT NULL AND p_lng IS NOT NULL
        AND COALESCE(a.doro_lat, a.jibun_lat, a.lat) IS NOT NULL THEN
        abs(COALESCE(a.doro_lat, a.jibun_lat, a.lat) - p_lat) + abs(COALESCE(a.doro_lon, a.jibun_lon, a.lon) - p_lng)
      ELSE 0
    END
  LIMIT 5;
END;
$$;
