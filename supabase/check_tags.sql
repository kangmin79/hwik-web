-- 동대문구 상가 월세 매물 태그 확인
SELECT id, property->>'price' as price, property->>'location' as location,
  property->>'complex' as complex, deposit, monthly_rent, tags
FROM cards
WHERE tags @> '["동대문구", "상가", "월세"]'::jsonb
AND trade_status = '계약가능'
ORDER BY created_at DESC
LIMIT 10;
