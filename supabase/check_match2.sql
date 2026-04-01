-- 동대문구 상가 월세 중 보증금 2600이하 (30% 여유) 매물
SELECT id, property->>'price' as price, property->>'location' as loc,
  property->>'complex' as complex, deposit, monthly_rent
FROM cards
WHERE tags @> '["동대문구", "상가", "월세"]'::jsonb
AND trade_status = '계약가능'
AND deposit <= 2600
ORDER BY deposit ASC, monthly_rent ASC
LIMIT 20;
