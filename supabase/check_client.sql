SELECT id, property->>'price' as price, property->>'location' as loc,
  wanted_trade_type, deposit, monthly_rent, price_number, tags
FROM cards
WHERE property->>'type' = '손님'
AND property->>'location' ILIKE '%청량리%'
LIMIT 3;
