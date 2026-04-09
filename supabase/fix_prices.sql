-- 1. monthly_rent 단위 오류 수정 (원 → 만원): 10000 이상이면 /10000
UPDATE cards
SET monthly_rent = monthly_rent / 10000
WHERE monthly_rent > 10000;

-- 2. price_number 재계산: property->>'price'에서 억/천/만 파싱
-- "4억" → 40000, "4억2000" → 42000, "2억5000" → 25000, "15억" → 150000
-- "8369만" → 8369, "11316만" → 11316
UPDATE cards
SET price_number =
  CASE
    -- 슬래시 패턴 (보/월): 보증금 부분만 추출
    WHEN property->>'price' LIKE '%/%' THEN
      CASE
        WHEN split_part(property->>'price', '/', 1) ~ '억' THEN
          (COALESCE(NULLIF(regexp_replace(split_part(split_part(property->>'price', '/', 1), '억', 1), '[^0-9.]', '', 'g'), '')::numeric, 0) * 10000 +
           COALESCE(NULLIF(regexp_replace(split_part(split_part(property->>'price', '/', 1), '억', 2), '[^0-9]', '', 'g'), '')::int, 0))::bigint
        ELSE
          COALESCE(NULLIF(regexp_replace(split_part(property->>'price', '/', 1), '[^0-9]', '', 'g'), '')::bigint, price_number)
      END
    -- 억 단위
    WHEN property->>'price' ~ '억' THEN
      (COALESCE(NULLIF(regexp_replace(split_part(property->>'price', '억', 1), '[^0-9.]', '', 'g'), '')::numeric, 0) * 10000 +
       COALESCE(NULLIF(regexp_replace(split_part(property->>'price', '억', 2), '[^0-9]', '', 'g'), '')::int, 0))::bigint
    -- 천 단위
    WHEN property->>'price' ~ '천' AND NOT property->>'price' ~ '억' THEN
      (COALESCE(NULLIF(regexp_replace(split_part(property->>'price', '천', 1), '[^0-9]', '', 'g'), '')::int, 0) * 1000 +
       COALESCE(NULLIF(regexp_replace(split_part(property->>'price', '천', 2), '[^0-9]', '', 'g'), '')::int, 0))::bigint
    -- 만 단위
    WHEN property->>'price' ~ '만' THEN
      COALESCE(NULLIF(regexp_replace(property->>'price', '[^0-9]', '', 'g'), '')::bigint, price_number)
    -- 숫자만
    ELSE price_number
  END
WHERE property->>'price' IS NOT NULL
  AND property->>'type' != '손님'
  AND property->>'price' ~ '[0-9]';

-- 3. deposit 재계산: 슬래시 패턴의 보증금도 동일 로직
UPDATE cards
SET deposit =
  CASE
    WHEN split_part(property->>'price', '/', 1) ~ '억' THEN
      (COALESCE(NULLIF(regexp_replace(split_part(split_part(property->>'price', '/', 1), '억', 1), '[^0-9.]', '', 'g'), '')::numeric, 0) * 10000 +
       COALESCE(NULLIF(regexp_replace(split_part(split_part(property->>'price', '/', 1), '억', 2), '[^0-9]', '', 'g'), '')::int, 0))::bigint
    ELSE
      COALESCE(NULLIF(regexp_replace(split_part(property->>'price', '/', 1), '[^0-9]', '', 'g'), '')::bigint, deposit)
  END,
  monthly_rent = COALESCE(NULLIF(regexp_replace(split_part(property->>'price', '/', 2), '[^0-9]', '', 'g'), '')::bigint, monthly_rent)
WHERE property->>'price' LIKE '%/%'
  AND property->>'type' != '손님';
