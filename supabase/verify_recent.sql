-- 최근 등록된 매물 10건 태그 확인
SELECT id, property->>'type' as type, property->>'price' as price,
  property->>'location' as loc, property->>'complex' as complex,
  property->>'category' as category, property->>'area' as area,
  property->>'floor' as floor,
  property->>'features' as features,
  price_number, deposit, monthly_rent, wanted_trade_type,
  tags, created_at
FROM cards
ORDER BY created_at DESC
LIMIT 10;
