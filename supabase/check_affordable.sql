-- 동대문구 상가 월세 중 보증금 2000이하 AND 월세 30이하
SELECT id, property->>'price' as price, property->>'location' as location,
  property->>'complex' as complex, deposit, monthly_rent
FROM cards
WHERE tags @> '["동대문구", "상가", "월세"]'::jsonb
AND trade_status = '계약가능'
AND deposit <= 2000
AND monthly_rent <= 30
LIMIT 10;

-- 보증금 2000이하만
SELECT COUNT(*) FROM cards
WHERE tags @> '["동대문구", "상가", "월세"]'::jsonb
AND trade_status = '계약가능'
AND deposit <= 2000;
