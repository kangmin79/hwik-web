-- 기존 손님 카드: price 텍스트에서 wanted_trade_type 추출
UPDATE cards SET wanted_trade_type = '월세'
WHERE property->>'type' = '손님'
AND wanted_trade_type IS NULL
AND (property->>'price' ILIKE '%월세%' OR property->>'price' LIKE '%/%');

UPDATE cards SET wanted_trade_type = '전세'
WHERE property->>'type' = '손님'
AND wanted_trade_type IS NULL
AND property->>'price' ILIKE '%전세%';

UPDATE cards SET wanted_trade_type = '매매'
WHERE property->>'type' = '손님'
AND wanted_trade_type IS NULL
AND (property->>'price' ILIKE '%매매%' OR property->>'price' ILIKE '%매도%');

-- 태그에 거래유형 추가
UPDATE cards SET tags = tags || to_jsonb(wanted_trade_type)
WHERE property->>'type' = '손님'
AND wanted_trade_type IS NOT NULL
AND NOT tags @> to_jsonb(wanted_trade_type);
