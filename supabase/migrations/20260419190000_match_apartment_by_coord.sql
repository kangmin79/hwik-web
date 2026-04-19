-- 좌표 기반 단지 매칭 RPC
-- 중개사 주소(도로명 or 지번) → 카카오 geocode → 이 RPC 호출
-- p_addr_type='doro' → apartments.doro_lat/lon과 거리 계산
-- p_addr_type='jibun' → apartments.jibun_lat/lon과 거리 계산
-- 반경 내 단지 반환 (가장 가까운 순)

CREATE OR REPLACE FUNCTION match_apartment_by_coord(
  p_lat float8,
  p_lng float8,
  p_radius_m integer DEFAULT 50,
  p_addr_type text DEFAULT 'doro'
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
  distance_m float8
) LANGUAGE plpgsql AS $$
DECLARE
  lat_range float8;
  lng_range float8;
BEGIN
  -- 반경에 해당하는 bounding box (인덱스 활용 위해)
  lat_range := p_radius_m / 111000.0;
  lng_range := p_radius_m / (88000.0 * cos(radians(p_lat)));

  IF p_addr_type = 'jibun' THEN
    RETURN QUERY
    SELECT
      a.kapt_code, a.kapt_name, a.sgg, a.umd_nm, a.doro_juso, a.property_type,
      a.jibun_lat, a.jibun_lon,
      (6371000 * acos(
        LEAST(1.0, GREATEST(-1.0,
          cos(radians(p_lat)) * cos(radians(a.jibun_lat)) *
          cos(radians(a.jibun_lon) - radians(p_lng)) +
          sin(radians(p_lat)) * sin(radians(a.jibun_lat))
        ))
      ))::float8 AS distance_m
    FROM apartments a
    WHERE a.jibun_lat IS NOT NULL
      AND a.jibun_lon IS NOT NULL
      AND a.jibun_lat BETWEEN p_lat - lat_range AND p_lat + lat_range
      AND a.jibun_lon BETWEEN p_lng - lng_range AND p_lng + lng_range
    ORDER BY distance_m ASC
    LIMIT 10;
  ELSE
    RETURN QUERY
    SELECT
      a.kapt_code, a.kapt_name, a.sgg, a.umd_nm, a.doro_juso, a.property_type,
      a.doro_lat, a.doro_lon,
      (6371000 * acos(
        LEAST(1.0, GREATEST(-1.0,
          cos(radians(p_lat)) * cos(radians(a.doro_lat)) *
          cos(radians(a.doro_lon) - radians(p_lng)) +
          sin(radians(p_lat)) * sin(radians(a.doro_lat))
        ))
      ))::float8 AS distance_m
    FROM apartments a
    WHERE a.doro_lat IS NOT NULL
      AND a.doro_lon IS NOT NULL
      AND a.doro_lat BETWEEN p_lat - lat_range AND p_lat + lat_range
      AND a.doro_lon BETWEEN p_lng - lng_range AND p_lng + lng_range
    ORDER BY distance_m ASC
    LIMIT 10;
  END IF;
END;
$$;
