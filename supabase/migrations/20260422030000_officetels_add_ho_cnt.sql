-- officetels: 호수(hoCnt) 컬럼 추가
-- 오피스텔은 업무시설이라 세대수(hhldCnt)가 아닌 호수(hoCnt)가 실제 호실 개수
-- hhldCnt 는 주거복합형 오피스텔의 주거세대만 카운트되어 대부분 0
-- backfill: officetel_test/backfill_ho_cnt.py + backfill_title_by_api.py 로 8,323건 적재 완료

ALTER TABLE officetels
  ADD COLUMN IF NOT EXISTS ho_cnt int;
