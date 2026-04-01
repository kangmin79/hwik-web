-- 손님 카드 확인 (동대문구 청량리동 상가 월세)
SELECT id, property->>'type' as type, property->>'price' as price,
  property->>'location' as location, property->>'category' as category,
  price_number, deposit, monthly_rent, wanted_trade_type, tags
FROM cards
WHERE property->>'type' = '손님'
AND property->>'location' ILIKE '%동대문%'
LIMIT 5;

-- 동대문구 상가 월세 매물 전체 확인
SELECT id, property->>'type' as type, property->>'price' as price,
  property->>'location' as location, property->>'complex' as complex,
  property->>'category' as category, price_number, deposit, monthly_rent, tags,
  trade_status
FROM cards
WHERE property->>'type' = '월세'
AND property->>'location' ILIKE '%동대문%'
AND trade_status = '계약가능'
ORDER BY created_at DESC
LIMIT 20;
