-- 기존 매물에 기본 태그 일괄 생성 (SQL로 직접)
UPDATE cards SET tags = (
  SELECT jsonb_agg(DISTINCT tag) FROM (
    -- 서울
    SELECT '서울' as tag
    UNION ALL
    -- 구
    SELECT (regexp_match(property->>'location', '([가-힣]+구)'))[1]
    WHERE property->>'location' IS NOT NULL
    UNION ALL
    -- 동
    SELECT (regexp_match(property->>'location', '([가-힣]+동)'))[1]
    WHERE property->>'location' IS NOT NULL
    UNION ALL
    -- 거래유형
    SELECT property->>'type'
    WHERE property->>'type' IN ('매매','전세','월세')
    UNION ALL
    -- 카테고리
    SELECT CASE property->>'category'
      WHEN 'apartment' THEN '아파트'
      WHEN 'officetel' THEN '오피스텔'
      WHEN 'room' THEN '원투룸'
      WHEN 'commercial' THEN '상가'
      WHEN 'office' THEN '사무실'
      ELSE NULL
    END
    WHERE property->>'category' IS NOT NULL
    UNION ALL
    -- 단지명
    SELECT TRIM(REPLACE(REPLACE(property->>'complex', '아파트', ''), '오피스텔', ''))
    WHERE property->>'complex' IS NOT NULL
    AND LENGTH(TRIM(REPLACE(REPLACE(property->>'complex', '아파트', ''), '오피스텔', ''))) >= 2
  ) sub WHERE tag IS NOT NULL AND tag != ''
)
WHERE (tags IS NULL OR tags = '[]'::jsonb)
AND property IS NOT NULL;
