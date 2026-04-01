SELECT COUNT(*) as total, COUNT(CASE WHEN tags IS NOT NULL AND tags != '[]'::jsonb THEN 1 END) as has_tags FROM cards;
