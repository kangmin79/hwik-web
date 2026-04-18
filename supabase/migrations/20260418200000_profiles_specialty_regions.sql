-- 중개사 전문 지역 (최대 3개) 컬럼 추가
-- 기존 address 파싱 fallback은 유지하되, 명시적 지정값이 있으면 우선 사용
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS specialty_regions text[] DEFAULT NULL;

COMMENT ON COLUMN profiles.specialty_regions IS '중개사가 선택한 전문 지역 배열, 최대 3개 (예: ARRAY[''중랑구'',''노원구''])';
