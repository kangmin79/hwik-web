-- 1. 태그 커버리지
SELECT
  COUNT(*) as total,
  COUNT(CASE WHEN tags IS NOT NULL AND tags != '[]'::jsonb THEN 1 END) as has_tags,
  COUNT(CASE WHEN tags IS NULL OR tags = '[]'::jsonb THEN 1 END) as no_tags
FROM cards;

-- 2. 태그 샘플 (매물)
SELECT id, property->>'type' as type, property->>'location' as loc,
  property->>'complex' as complex, tags
FROM cards
WHERE property->>'type' != '손님'
AND tags IS NOT NULL AND tags != '[]'::jsonb
ORDER BY created_at DESC LIMIT 3;

-- 3. 태그 샘플 (손님)
SELECT id, property->>'type' as type, property->>'location' as loc,
  wanted_trade_type, tags, required_tags, excluded_tags
FROM cards
WHERE property->>'type' = '손님'
AND tags IS NOT NULL AND tags != '[]'::jsonb
ORDER BY created_at DESC LIMIT 3;

-- 4. GIN 인덱스 확인
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'cards' AND indexname LIKE '%tags%';

-- 5. 태그 기반 검색 테스트 (강북구 월세)
SELECT COUNT(*) as match_count
FROM cards
WHERE tags @> '["강북구", "월세"]'::jsonb
AND trade_status = '계약가능';
