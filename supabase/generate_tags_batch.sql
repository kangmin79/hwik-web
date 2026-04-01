-- 태그 없는 카드 수 확인
SELECT COUNT(*) as total,
  COUNT(CASE WHEN tags IS NULL OR tags = '[]'::jsonb THEN 1 END) as no_tags
FROM cards;
