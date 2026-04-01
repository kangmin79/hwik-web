-- 오늘 이후 등록된 카드
SELECT id, property->>'type' as type, property->>'price' as price,
  property->>'location' as loc, property->>'category' as cat,
  property->>'features' as features,
  price_number, deposit, monthly_rent, tags, created_at
FROM cards
WHERE created_at >= '2026-04-01'
ORDER BY created_at DESC
LIMIT 5;

-- 3/31 이후 등록 카드
SELECT id, property->>'type' as type, property->>'price' as price,
  price_number, deposit, monthly_rent, tags, created_at
FROM cards
WHERE created_at >= '2026-03-31'
ORDER BY created_at DESC
LIMIT 5;
