-- officetels: 건축물대장 표제부 추가 필드
ALTER TABLE officetels
  ADD COLUMN IF NOT EXISTS parking_total     int,     -- 자주식+기계식 총 주차대수
  ADD COLUMN IF NOT EXISTS parking_self      int,     -- 자주식(옥내자동+옥외자동)
  ADD COLUMN IF NOT EXISTS parking_mech      int,     -- 기계식(옥내기계+옥외기계)
  ADD COLUMN IF NOT EXISTS elevator_ride     int,     -- 승용 승강기 수
  ADD COLUMN IF NOT EXISTS elevator_emgen    int,     -- 비상용 승강기 수
  ADD COLUMN IF NOT EXISTS strct_name        text,    -- 구조 (철근콘크리트구조 등)
  ADD COLUMN IF NOT EXISTS bc_ratio          real,    -- 건폐율 %
  ADD COLUMN IF NOT EXISTS vl_ratio          real,    -- 용적률 %
  ADD COLUMN IF NOT EXISTS earthquake_rating text;    -- 내진설계 강도 원문
