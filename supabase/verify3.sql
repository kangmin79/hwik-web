SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'cards' AND indexname LIKE '%tags%';
