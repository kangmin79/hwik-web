-- 이 손님의 agent_id 확인
SELECT id, agent_id, property->>'location' as loc FROM cards
WHERE property->>'type' = '손님' AND property->>'location' ILIKE '%청량리%'
LIMIT 3;

-- 해당 중개사의 동대문구 상가 월세 매물
SELECT id, property->>'price' as price, deposit, monthly_rent, agent_id
FROM cards
WHERE agent_id = (SELECT agent_id FROM cards WHERE property->>'type' = '손님' AND property->>'location' ILIKE '%청량리%' LIMIT 1)
AND tags @> '["동대문구", "상가", "월세"]'::jsonb
AND trade_status = '계약가능'
ORDER BY deposit ASC
LIMIT 10;
