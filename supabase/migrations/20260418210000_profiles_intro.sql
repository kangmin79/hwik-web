-- 중개사 인사말 한 줄 컬럼 추가 (홈 상단 노출용)
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS intro text DEFAULT NULL;

COMMENT ON COLUMN profiles.intro IS '중개사 인사말 한 줄 (30~60자 권장, 홈 헤더 노출)';
