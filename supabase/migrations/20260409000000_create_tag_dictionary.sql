-- ═══════════════════════════════════════════════════════════
-- 휙 태그 사전 (tag_dictionary)
-- 모든 시스템 태그의 의미·동의어·메타데이터를 한곳에 관리
-- ═══════════════════════════════════════════════════════════

create table if not exists tag_dictionary (
  tag         text primary key,           -- 표준 태그명 ('매매', '강남구', '5~10평' 등)
  category    text not null,              -- 카테고리 (아래 참조)
  display     text,                       -- 사용자 표시명 (null이면 tag 그대로)
  description text,                       -- 태그 의미 설명
  synonyms    text[] default '{}',        -- 이 태그로 변환되는 동의어 목록
  metadata    jsonb default '{}',         -- 카테고리별 추가 정보
  usage_count int default 0,             -- 실제 사용 횟수 (cards에서 집계)
  is_active   boolean default true,       -- 비활성화 가능
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- 카테고리 인덱스 (카테고리별 조회)
create index if not exists idx_tag_dict_category on tag_dictionary(category);

-- updated_at 자동 갱신
create or replace function update_tag_dictionary_timestamp()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger tag_dictionary_updated
  before update on tag_dictionary
  for each row execute function update_tag_dictionary_timestamp();

-- RLS
alter table tag_dictionary enable row level security;

-- 누구나 읽기 가능 (태그 사전은 공개 데이터)
create policy "tag_dictionary_read" on tag_dictionary
  for select using (true);

-- 관리자만 수정 (is_admin 체크)
create policy "tag_dictionary_admin_write" on tag_dictionary
  for all using (
    exists (select 1 from profiles where id = auth.uid() and is_admin = true)
  );

-- ═══════════════════════════════════════════════════════════
-- 카테고리 설명:
--   region_city     — 광역시도 (서울, 인천, 경기 등)
--   region_district — 구/시 (강남구, 수원시 등)
--   trade_type      — 거래유형 (매매, 전세, 월세, 반전세)
--   property_type   — 매물유형 (아파트, 오피스텔, 원투룸 등)
--   price_sale      — 매매/전세 가격대
--   price_deposit   — 월세 보증금대
--   price_monthly   — 월세대
--   area            — 면적대
--   floor           — 층수대
--   room            — 방구조
--   direction       — 방향
--   movein          — 입주시기
--   transport       — 교통
--   subway          — 지하철 노선
--   education       — 교육
--   view            — 전망/뷰
--   environment     — 주변환경
--   security        — 보안
--   structure       — 건물구조
--   facility        — 시설/옵션
--   finance         — 금융조건
--   commercial      — 상가 전용
--   special         — 특수조건
--   neologism       — 부동산 신조어
--   price_flex      — 가격 협의
-- ═══════════════════════════════════════════════════════════

-- ── 1. 광역시도 (region_city) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('서울', 'region_city', '서울특별시', '대한민국 수도, 25개 자치구', '{}', '{"code":"11","districts":25}'),
  ('인천', 'region_city', '인천광역시', '서해안 최대 항구도시, 10개 구/군', '{}', '{"code":"28","districts":10}'),
  ('경기', 'region_city', '경기도', '수도권 광역도, 31개 시/군', '{}', '{"code":"41","districts":31}'),
  ('부산', 'region_city', '부산광역시', '대한민국 제2도시, 16개 구/군', '{}', '{"code":"26","districts":16}'),
  ('대구', 'region_city', '대구광역시', '영남 내륙 중심, 8개 구/군', '{}', '{"code":"27","districts":8}'),
  ('대전', 'region_city', '대전광역시', '충청권 중심, 5개 구', '{}', '{"code":"30","districts":5}'),
  ('광주', 'region_city', '광주광역시', '호남 중심, 5개 구', '{}', '{"code":"29","districts":5}'),
  ('울산', 'region_city', '울산광역시', '산업도시, 5개 구/군', '{}', '{"code":"31","districts":5}'),
  ('세종', 'region_city', '세종특별자치시', '행정수도', '{}', '{"code":"36","districts":0}')
on conflict (tag) do nothing;

-- ── 2. 서울 25개 구 (region_district) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('강남구', 'region_district', '강남구', '서울 동남권, 대치·역삼·논현·압구정·청담', '{"강남"}', '{"city":"서울","code":"11680"}'),
  ('서초구', 'region_district', '서초구', '서울 서남권, 서초·반포·잠원·방배·양재', '{"서초"}', '{"city":"서울","code":"11650"}'),
  ('송파구', 'region_district', '송파구', '서울 동남권, 잠실·방이·문정·가락·석촌', '{"송파"}', '{"city":"서울","code":"11710"}'),
  ('마포구', 'region_district', '마포구', '서울 서북권, 합정·연남·상수·망원·성산', '{"마포"}', '{"city":"서울","code":"11440"}'),
  ('용산구', 'region_district', '용산구', '서울 중심, 이태원·한남·이촌·후암', '{"용산"}', '{"city":"서울","code":"11170"}'),
  ('성동구', 'region_district', '성동구', '서울 동부, 성수·왕십리·금호', '{"성동"}', '{"city":"서울","code":"11200"}'),
  ('광진구', 'region_district', '광진구', '서울 동부, 건대·자양·구의', '{"광진"}', '{"city":"서울","code":"11215"}'),
  ('영등포구', 'region_district', '영등포구', '서울 서남권, 여의도·당산·영등포', '{"영등포"}', '{"city":"서울","code":"11560"}'),
  ('강동구', 'region_district', '강동구', '서울 동부, 길동·강일·고덕·암사·둔촌', '{"강동"}', '{"city":"서울","code":"11740"}'),
  ('동작구', 'region_district', '동작구', '서울 남부, 사당·노량진·흑석', '{"동작"}', '{"city":"서울","code":"11590"}'),
  ('관악구', 'region_district', '관악구', '서울 남부, 신림·봉천·서울대입구', '{"관악"}', '{"city":"서울","code":"11620"}'),
  ('종로구', 'region_district', '종로구', '서울 도심, 광화문·인사동·종로', '{"종로"}', '{"city":"서울","code":"11110"}'),
  ('중구', 'region_district', '중구', '서울 도심, 을지로·명동·충무로', '{}', '{"city":"서울","code":"11140"}'),
  ('강서구', 'region_district', '강서구', '서울 서부, 마곡·발산·화곡', '{"강서"}', '{"city":"서울","code":"11500"}'),
  ('양천구', 'region_district', '양천구', '서울 서부, 목동·신월', '{"양천"}', '{"city":"서울","code":"11470"}'),
  ('구로구', 'region_district', '구로구', '서울 남서부, 구로디지털단지·개봉', '{"구로"}', '{"city":"서울","code":"11530"}'),
  ('노원구', 'region_district', '노원구', '서울 북부, 상계·중계·하계·공릉', '{"노원"}', '{"city":"서울","code":"11350"}'),
  ('서대문구', 'region_district', '서대문구', '서울 서북, 연희·신촌·홍제', '{"서대문"}', '{"city":"서울","code":"11410"}'),
  ('은평구', 'region_district', '은평구', '서울 서북, 불광·응암·갈현', '{"은평"}', '{"city":"서울","code":"11380"}'),
  ('중랑구', 'region_district', '중랑구', '서울 동북, 면목·상봉·중화·묵동·신내', '{"중랑"}', '{"city":"서울","code":"11260"}'),
  ('도봉구', 'region_district', '도봉구', '서울 북부, 도봉·창동·방학', '{"도봉"}', '{"city":"서울","code":"11320"}'),
  ('동대문구', 'region_district', '동대문구', '서울 동북, 장안·전농·이문·회기', '{"동대문"}', '{"city":"서울","code":"11230"}'),
  ('성북구', 'region_district', '성북구', '서울 북부, 길음·돈암·정릉', '{"성북"}', '{"city":"서울","code":"11290"}'),
  ('금천구', 'region_district', '금천구', '서울 남서, 가산디지털단지·독산', '{"금천"}', '{"city":"서울","code":"11545"}'),
  ('강북구', 'region_district', '강북구', '서울 북부, 미아·수유·번동', '{"강북"}', '{"city":"서울","code":"11305"}')
on conflict (tag) do nothing;

-- ── 3. 인천 10개 구/군 ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('미추홀구', 'region_district', '미추홀구', '인천 구도심, 주안·숭의', '{}', '{"city":"인천"}'),
  ('연수구', 'region_district', '연수구', '인천 신도시, 송도·연수', '{}', '{"city":"인천"}'),
  ('남동구', 'region_district', '남동구', '인천 동남, 구월·만수·간석', '{}', '{"city":"인천"}'),
  ('부평구', 'region_district', '부평구', '인천 북부, 부평역·삼산', '{}', '{"city":"인천"}'),
  ('계양구', 'region_district', '계양구', '인천 북부, 계산·작전', '{}', '{"city":"인천"}'),
  ('강화군', 'region_district', '강화군', '인천 강화도', '{}', '{"city":"인천"}'),
  ('옹진군', 'region_district', '옹진군', '인천 도서지역', '{}', '{"city":"인천"}')
on conflict (tag) do nothing;

-- 인천 동구/서구/중구는 다른 도시에도 있어서 synonyms에 도시 정보 포함
-- (실제 태그로는 잘 안 쓰이지만 완전성을 위해 포함)

-- ── 4. 경기 31개 시/군 ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('수원시', 'region_district', '수원시', '경기 남부, 4개 구 (장안·권선·팔달·영통)', '{}', '{"city":"경기"}'),
  ('성남시', 'region_district', '성남시', '경기 남부, 분당·수정·중원', '{}', '{"city":"경기"}'),
  ('의정부시', 'region_district', '의정부시', '경기 북부 중심', '{}', '{"city":"경기"}'),
  ('안양시', 'region_district', '안양시', '경기 남부, 만안·동안', '{}', '{"city":"경기"}'),
  ('부천시', 'region_district', '부천시', '경기 서부, 소사·오정', '{}', '{"city":"경기"}'),
  ('광명시', 'region_district', '광명시', '경기 서부, KTX광명역', '{}', '{"city":"경기"}'),
  ('평택시', 'region_district', '평택시', '경기 남부', '{}', '{"city":"경기"}'),
  ('동두천시', 'region_district', '동두천시', '경기 최북단', '{}', '{"city":"경기"}'),
  ('안산시', 'region_district', '안산시', '경기 서남, 상록·단원', '{}', '{"city":"경기"}'),
  ('고양시', 'region_district', '고양시', '경기 서북, 덕양·일산동·일산서', '{}', '{"city":"경기"}'),
  ('과천시', 'region_district', '과천시', '경기 중부, 정부과천청사', '{}', '{"city":"경기"}'),
  ('구리시', 'region_district', '구리시', '경기 동부', '{}', '{"city":"경기"}'),
  ('남양주시', 'region_district', '남양주시', '경기 동북', '{}', '{"city":"경기"}'),
  ('오산시', 'region_district', '오산시', '경기 남부', '{}', '{"city":"경기"}'),
  ('시흥시', 'region_district', '시흥시', '경기 서남', '{}', '{"city":"경기"}'),
  ('군포시', 'region_district', '군포시', '경기 남부', '{}', '{"city":"경기"}'),
  ('의왕시', 'region_district', '의왕시', '경기 남부', '{}', '{"city":"경기"}'),
  ('하남시', 'region_district', '하남시', '경기 동부, 미사', '{}', '{"city":"경기"}'),
  ('용인시', 'region_district', '용인시', '경기 남부, 처인·기흥·수지', '{}', '{"city":"경기"}'),
  ('파주시', 'region_district', '파주시', '경기 서북', '{}', '{"city":"경기"}'),
  ('이천시', 'region_district', '이천시', '경기 동남', '{}', '{"city":"경기"}'),
  ('안성시', 'region_district', '안성시', '경기 남부', '{}', '{"city":"경기"}'),
  ('김포시', 'region_district', '김포시', '경기 서부, 한강신도시', '{}', '{"city":"경기"}'),
  ('화성시', 'region_district', '화성시', '경기 남서, 동탄', '{}', '{"city":"경기"}'),
  ('광주시', 'region_district', '광주시', '경기 동남 (광주광역시와 다름)', '{}', '{"city":"경기"}'),
  ('양주시', 'region_district', '양주시', '경기 북부', '{}', '{"city":"경기"}'),
  ('포천시', 'region_district', '포천시', '경기 북부', '{}', '{"city":"경기"}'),
  ('여주시', 'region_district', '여주시', '경기 동남', '{}', '{"city":"경기"}'),
  ('연천군', 'region_district', '연천군', '경기 최북단', '{}', '{"city":"경기"}'),
  ('가평군', 'region_district', '가평군', '경기 동북', '{}', '{"city":"경기"}'),
  ('양평군', 'region_district', '양평군', '경기 동부', '{}', '{"city":"경기"}')
on conflict (tag) do nothing;

-- ── 5. 경기 시 내 구 (19개) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('장안구', 'region_district', '장안구', '수원시 북부', '{}', '{"city":"경기","parent":"수원시"}'),
  ('권선구', 'region_district', '권선구', '수원시 서남', '{}', '{"city":"경기","parent":"수원시"}'),
  ('팔달구', 'region_district', '팔달구', '수원시 중심', '{}', '{"city":"경기","parent":"수원시"}'),
  ('영통구', 'region_district', '영통구', '수원시 동남, 광교', '{}', '{"city":"경기","parent":"수원시"}'),
  ('수정구', 'region_district', '수정구', '성남시 남부', '{}', '{"city":"경기","parent":"성남시"}'),
  ('중원구', 'region_district', '중원구', '성남시 중부', '{}', '{"city":"경기","parent":"성남시"}'),
  ('분당구', 'region_district', '분당구', '성남시 분당신도시', '{}', '{"city":"경기","parent":"성남시"}'),
  ('만안구', 'region_district', '만안구', '안양시 남부', '{}', '{"city":"경기","parent":"안양시"}'),
  ('동안구', 'region_district', '동안구', '안양시 동부, 평촌', '{}', '{"city":"경기","parent":"안양시"}'),
  ('소사구', 'region_district', '소사구', '부천시 남부', '{}', '{"city":"경기","parent":"부천시"}'),
  ('오정구', 'region_district', '오정구', '부천시 북부', '{}', '{"city":"경기","parent":"부천시"}'),
  ('상록구', 'region_district', '상록구', '안산시 동부', '{}', '{"city":"경기","parent":"안산시"}'),
  ('단원구', 'region_district', '단원구', '안산시 서부', '{}', '{"city":"경기","parent":"안산시"}'),
  ('덕양구', 'region_district', '덕양구', '고양시 남부', '{}', '{"city":"경기","parent":"고양시"}'),
  ('일산동구', 'region_district', '일산동구', '고양시 일산 동쪽', '{}', '{"city":"경기","parent":"고양시"}'),
  ('일산서구', 'region_district', '일산서구', '고양시 일산 서쪽', '{}', '{"city":"경기","parent":"고양시"}'),
  ('처인구', 'region_district', '처인구', '용인시 남부', '{}', '{"city":"경기","parent":"용인시"}'),
  ('기흥구', 'region_district', '기흥구', '용인시 중부', '{}', '{"city":"경기","parent":"용인시"}'),
  ('수지구', 'region_district', '수지구', '용인시 북부', '{}', '{"city":"경기","parent":"용인시"}')
on conflict (tag) do nothing;

-- ── 6. 거래유형 (trade_type) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('매매', 'trade_type', '매매', '소유권 이전 거래', '{"ㅁㅁ","매도","분양","사려","매입","구매","직거래"}', '{"weight":30}'),
  ('전세', 'trade_type', '전세', '보증금 전액 납부 후 거주, 월세 없음', '{"ㅈㅅ","젼세","임차","전세권설정"}', '{"weight":30}'),
  ('월세', 'trade_type', '월세', '보증금 + 매월 임대료 납부', '{"ㅇㅅ","웜세","렌트","빌려","임대","달세"}', '{"weight":30}'),
  ('반전세', 'trade_type', '반전세', '보증금 높고 월세 낮은 형태', '{"준전세","보증금높은월세"}', '{"weight":30}')
on conflict (tag) do nothing;

-- ── 7. 매물유형 (property_type) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('아파트', 'property_type', '아파트', '5층 이상 공동주택, 엘리베이터·관리소 있음', '{"apt","주상복합","단지형","대단지"}', '{"weight":20,"category_code":"apartment"}'),
  ('오피스텔', 'property_type', '오피스텔', '업무+주거 겸용 건물, 1인 가구 많음', '{"옵텔","officetel"}', '{"weight":20,"category_code":"officetel"}'),
  ('원투룸', 'property_type', '원투룸', '소형 주거공간 통칭 (원룸~투룸)', '{}', '{"weight":20,"category_code":"room"}'),
  ('상가', 'property_type', '상가', '상업용 점포', '{"점포","매장","식당","카페","편의점","치킨집","미용실","약국","베이커리"}', '{"weight":20,"category_code":"commercial"}'),
  ('사무실', 'property_type', '사무실', '업무용 공간', '{"오피스","업무용","코워킹","지식산업센터"}', '{"weight":20,"category_code":"office"}'),
  ('빌라', 'property_type', '빌라', '4층 이하 다세대/연립 주택', '{"다세대","연립","다가구","신축빌라"}', '{"weight":20}'),
  ('원룸', 'property_type', '원룸', '방 1개 (주방·화장실 분리형 포함)', '{"1룸","1.5룸","스튜디오형"}', '{"weight":10}'),
  ('투룸', 'property_type', '투룸', '방 2개', '{"2룸"}', '{"weight":10}'),
  ('쓰리룸', 'property_type', '쓰리룸', '방 3개', '{"3룸"}', '{"weight":10}'),
  ('포룸이상', 'property_type', '4룸 이상', '방 4개 이상, 대형 평수', '{"4룸"}', '{"weight":10}'),
  ('주택', 'property_type', '주택', '단독주택·다가구주택·타운하우스', '{"단독주택","다가구주택","타운하우스"}', '{"weight":20}'),
  ('건물', 'property_type', '건물', '빌딩 전체 매매', '{"빌딩","꼬마빌딩"}', '{"weight":20}'),
  ('공장창고', 'property_type', '공장/창고', '물류·창고·공장 시설', '{"물류","창고","공장"}', '{"weight":20}'),
  ('토지', 'property_type', '토지', '대지·임야·전답', '{"대지","임야","전답"}', '{"weight":20}')
on conflict (tag) do nothing;

-- ── 8. 매매/전세 가격대 (price_sale) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('5천이하', 'price_sale', '5천만원 이하', '매매/전세 5,000만원 이하', '{}', '{"min":0,"max":5000,"unit":"만원","weight":25}'),
  ('5천~1억', 'price_sale', '5천~1억', '매매/전세 5,000만~1억', '{}', '{"min":5000,"max":10000,"unit":"만원","weight":25}'),
  ('1~2억', 'price_sale', '1~2억', '매매/전세 1억~2억', '{}', '{"min":10000,"max":20000,"unit":"만원","weight":25}'),
  ('2~3억', 'price_sale', '2~3억', '매매/전세 2억~3억', '{}', '{"min":20000,"max":30000,"unit":"만원","weight":25}'),
  ('3~5억', 'price_sale', '3~5억', '매매/전세 3억~5억', '{}', '{"min":30000,"max":50000,"unit":"만원","weight":25}'),
  ('5~7억', 'price_sale', '5~7억', '매매/전세 5억~7억', '{}', '{"min":50000,"max":70000,"unit":"만원","weight":25}'),
  ('7~10억', 'price_sale', '7~10억', '매매/전세 7억~10억', '{}', '{"min":70000,"max":100000,"unit":"만원","weight":25}'),
  ('10~15억', 'price_sale', '10~15억', '매매/전세 10억~15억', '{}', '{"min":100000,"max":150000,"unit":"만원","weight":25}'),
  ('15~20억', 'price_sale', '15~20억', '매매/전세 15억~20억', '{}', '{"min":150000,"max":200000,"unit":"만원","weight":25}'),
  ('20억이상', 'price_sale', '20억 이상', '매매/전세 20억 이상', '{}', '{"min":200000,"max":null,"unit":"만원","weight":25}')
on conflict (tag) do nothing;

-- ── 9. 월세 보증금대 (price_deposit) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('보증금500이하', 'price_deposit', '보증금 500만 이하', '월세 보증금 500만원 이하', '{}', '{"min":0,"max":500,"unit":"만원"}'),
  ('보증금500~1천', 'price_deposit', '보증금 500~1,000만', '월세 보증금 500~1,000만원', '{}', '{"min":500,"max":1000,"unit":"만원"}'),
  ('보증금1~2천', 'price_deposit', '보증금 1,000~2,000만', '월세 보증금 1,000~2,000만원', '{}', '{"min":1000,"max":2000,"unit":"만원"}'),
  ('보증금2~3천', 'price_deposit', '보증금 2,000~3,000만', '월세 보증금 2,000~3,000만원', '{}', '{"min":2000,"max":3000,"unit":"만원"}'),
  ('보증금3~5천', 'price_deposit', '보증금 3,000~5,000만', '월세 보증금 3,000~5,000만원', '{}', '{"min":3000,"max":5000,"unit":"만원"}'),
  ('보증금5천~1억', 'price_deposit', '보증금 5,000만~1억', '월세 보증금 5,000만~1억', '{}', '{"min":5000,"max":10000,"unit":"만원"}'),
  ('보증금1억이상', 'price_deposit', '보증금 1억 이상', '월세 보증금 1억 이상', '{}', '{"min":10000,"max":null,"unit":"만원"}')
on conflict (tag) do nothing;

-- ── 10. 월세대 (price_monthly) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('월세30이하', 'price_monthly', '월세 30만 이하', '월 임대료 30만원 이하', '{}', '{"min":0,"max":30,"unit":"만원/월"}'),
  ('월세30~50', 'price_monthly', '월세 30~50만', '월 임대료 30~50만원', '{}', '{"min":30,"max":50,"unit":"만원/월"}'),
  ('월세50~80', 'price_monthly', '월세 50~80만', '월 임대료 50~80만원', '{}', '{"min":50,"max":80,"unit":"만원/월"}'),
  ('월세80~100', 'price_monthly', '월세 80~100만', '월 임대료 80~100만원', '{}', '{"min":80,"max":100,"unit":"만원/월"}'),
  ('월세100~150', 'price_monthly', '월세 100~150만', '월 임대료 100~150만원', '{}', '{"min":100,"max":150,"unit":"만원/월"}'),
  ('월세150~200', 'price_monthly', '월세 150~200만', '월 임대료 150~200만원', '{}', '{"min":150,"max":200,"unit":"만원/월"}'),
  ('월세200이상', 'price_monthly', '월세 200만 이상', '월 임대료 200만원 이상', '{}', '{"min":200,"max":null,"unit":"만원/월"}')
on conflict (tag) do nothing;

-- ── 11. 면적대 (area) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('5평이하', 'area', '5평 이하', '전용 ~16.5㎡, 고시원/소형원룸', '{}', '{"min_pyeong":0,"max_pyeong":5,"min_sqm":0,"max_sqm":16.5,"weight":15}'),
  ('5~10평', 'area', '5~10평', '전용 16.5~33㎡, 원룸/소형오피스텔', '{}', '{"min_pyeong":5,"max_pyeong":10,"min_sqm":16.5,"max_sqm":33,"weight":15}'),
  ('10~15평', 'area', '10~15평', '전용 33~49.5㎡, 투룸/오피스텔', '{}', '{"min_pyeong":10,"max_pyeong":15,"min_sqm":33,"max_sqm":49.5,"weight":15}'),
  ('15~20평', 'area', '15~20평', '전용 49.5~66㎡, 소형아파트/넓은투룸', '{}', '{"min_pyeong":15,"max_pyeong":20,"min_sqm":49.5,"max_sqm":66,"weight":15}'),
  ('20~25평', 'area', '20~25평', '전용 66~82.5㎡, 중형아파트 (국민평수 84㎡ 근접)', '{}', '{"min_pyeong":20,"max_pyeong":25,"min_sqm":66,"max_sqm":82.5,"weight":15}'),
  ('25~30평', 'area', '25~30평', '전용 82.5~99㎡, 국민평수대~중대형', '{}', '{"min_pyeong":25,"max_pyeong":30,"min_sqm":82.5,"max_sqm":99,"weight":15}'),
  ('30~40평', 'area', '30~40평', '전용 99~132㎡, 대형아파트', '{}', '{"min_pyeong":30,"max_pyeong":40,"min_sqm":99,"max_sqm":132,"weight":15}'),
  ('40~50평', 'area', '40~50평', '전용 132~165㎡, 대형·고급', '{}', '{"min_pyeong":40,"max_pyeong":50,"min_sqm":132,"max_sqm":165,"weight":15}'),
  ('50평이상', 'area', '50평 이상', '전용 165㎡+, 초대형·펜트하우스급', '{}', '{"min_pyeong":50,"max_pyeong":null,"min_sqm":165,"max_sqm":null,"weight":15}'),
  ('40평이상', 'area', '40평 이상', '전용 132㎡+, 대형 (DB 호환용)', '{}', '{"min_pyeong":40,"max_pyeong":null,"min_sqm":132,"max_sqm":null,"weight":15}')
on conflict (tag) do nothing;

-- ── 12. 층수대 (floor) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('반지하', 'floor', '반지하', '지하~반지하층, 채광 불리', '{"B1","지하"}', '{"level":"sub","weight":5}'),
  ('1층', 'floor', '1층', '지상 1층, 접근성 좋지만 프라이버시 낮음', '{}', '{"level":1,"weight":5}'),
  ('저층', 'floor', '저층 (2~3F)', '2~3층, 엘리베이터 불필요', '{}', '{"level":"low","min":2,"max":3,"weight":5}'),
  ('중층', 'floor', '중층 (4~8F)', '4~8층, 무난한 선호도', '{}', '{"level":"mid","min":4,"max":8,"weight":5}'),
  ('고층', 'floor', '고층 (9~15F)', '9~15층, 전망·채광 양호', '{}', '{"level":"high","min":9,"max":15,"weight":5}'),
  ('초고층', 'floor', '초고층 (16F+)', '16층 이상, 전망 우수', '{}', '{"level":"ultra","min":16,"weight":5}'),
  ('옥탑', 'floor', '옥탑층', '최상층 옥탑, 테라스 가능', '{"탑층","펜트"}', '{"level":"rooftop","weight":5}'),
  ('복층', 'floor', '복층', '2개 층 연결 구조', '{}', '{"level":"duplex","weight":5}')
on conflict (tag) do nothing;

-- ── 13. 방향 (direction) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('남향', 'direction', '남향', '남쪽 향, 채광 최고 (가장 선호)', '{"정남향"}', '{"azimuth":180,"weight":5}'),
  ('동향', 'direction', '동향', '동쪽 향, 아침 햇살', '{"정동향"}', '{"azimuth":90,"weight":5}'),
  ('서향', 'direction', '서향', '서쪽 향, 오후 햇살 (서향빨)', '{"정서향"}', '{"azimuth":270,"weight":5}'),
  ('북향', 'direction', '북향', '북쪽 향, 채광 불리', '{"정북향"}', '{"azimuth":0,"weight":5}'),
  ('남동향', 'direction', '남동향', '남동쪽, 오전 채광 좋음', '{"동남향"}', '{"azimuth":135,"weight":5}'),
  ('남서향', 'direction', '남서향', '남서쪽, 오후 채광 좋음', '{"서남향"}', '{"azimuth":225,"weight":5}'),
  ('북동향', 'direction', '북동향', '북동쪽', '{"동북향"}', '{"azimuth":45,"weight":5}'),
  ('북서향', 'direction', '북서향', '북서쪽', '{"서북향"}', '{"azimuth":315,"weight":5}')
on conflict (tag) do nothing;

-- ── 14. 입주시기 (movein) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('즉시입주', 'movein', '즉시입주', '현재 공실, 바로 입주 가능', '{"즉입","바로입주","입주가능","공실"}', '{"weight":15}'),
  ('입주협의', 'movein', '입주협의', '입주 시기 조율 필요', '{"협의가능"}', '{"weight":15}'),
  ('2026상반기', 'movein', '2026 상반기', '2026년 1~6월 입주', '{}', '{"year":2026,"half":"H1","weight":15}'),
  ('2026하반기', 'movein', '2026 하반기', '2026년 7~12월 입주', '{}', '{"year":2026,"half":"H2","weight":15}'),
  ('2027상반기', 'movein', '2027 상반기', '2027년 1~6월 입주', '{}', '{"year":2027,"half":"H1","weight":15}'),
  ('2027하반기', 'movein', '2027 하반기', '2027년 7~12월 입주', '{}', '{"year":2027,"half":"H2","weight":15}')
on conflict (tag) do nothing;

-- ── 15. 교통 (transport) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('초역세권', 'transport', '초역세권', '지하철역 도보 1~5분 이내', '{"역도보1분","역도보2분","역바로앞"}', '{"walk_min":1,"walk_max":5,"weight":10}'),
  ('역세권', 'transport', '역세권', '지하철역 도보 10분 이내', '{"역도보","역에서","지하철근처","역앞","역근처"}', '{"walk_min":5,"walk_max":10,"weight":10}'),
  ('더블역세권', 'transport', '더블역세권', '2개 이상 노선 이용 가능', '{"트리플역세권","2개노선"}', '{"lines":2,"weight":10}'),
  ('대중교통편리', 'transport', '대중교통 편리', '버스·지하철 접근성 양호', '{"버스정류장","교통편리"}', '{"weight":10}'),
  ('대로변', 'transport', '대로변', '큰 도로 인접 (상가에 유리)', '{"큰길가","간선도로"}', '{"weight":10}'),
  ('GTX역세권', 'transport', 'GTX 역세권', 'GTX(수도권광역급행) 역 인근', '{"GTX","A노선","B노선","C노선"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 16. 지하철 노선 (subway) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('1호선', 'subway', '1호선', '수도권 1호선 (서울역~인천/천안)', '{}', '{"color":"#0052A4"}'),
  ('2호선', 'subway', '2호선', '서울 순환선 (강남·홍대·을지로)', '{}', '{"color":"#00A84D"}'),
  ('3호선', 'subway', '3호선', '수서~대화 (교대·양재·일산)', '{}', '{"color":"#EF7C1C"}'),
  ('4호선', 'subway', '4호선', '당고개~오이도 (명동·사당)', '{}', '{"color":"#00A5DE"}'),
  ('5호선', 'subway', '5호선', '방화~마천/하남 (여의도·강동)', '{}', '{"color":"#996CAC"}'),
  ('6호선', 'subway', '6호선', '응암순환~신내 (이태원·합정)', '{}', '{"color":"#CD7C2F"}'),
  ('7호선', 'subway', '7호선', '장암~석남 (강남·건대·노원)', '{}', '{"color":"#747F00"}'),
  ('8호선', 'subway', '8호선', '암사~모란 (잠실·가락)', '{}', '{"color":"#E6186C"}'),
  ('9호선', 'subway', '9호선', '개화~중앙보훈병원 (여의도·강남)', '{}', '{"color":"#BDB092"}'),
  ('신분당선', 'subway', '신분당선', '신사~광교 (강남·판교·광교)', '{}', '{"color":"#D31145"}'),
  ('경의중앙선', 'subway', '경의중앙선', '문산~용문 (홍대·왕십리)', '{}', '{"color":"#77C4A3"}'),
  ('분당선', 'subway', '분당선', '왕십리~수원 (서현·야탑)', '{}', '{"color":"#F5A200"}')
on conflict (tag) do nothing;

-- ── 17. 교육 (education) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('학군좋음', 'education', '학군 좋음', '초·중·고 학군 우수 지역', '{"학교근처","학교앞","초등학교","중학교","명문학군","교육환경"}', '{"weight":10}'),
  ('학원가', 'education', '학원가', '학원 밀집 지역 (대치·목동 등)', '{"학원밀집"}', '{"weight":10}'),
  ('학세권', 'education', '학세권', '대학교 인근 (임대수요 높음)', '{"대학교근처","대학가"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 18. 전망/뷰 (view) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('한강뷰', 'view', '한강뷰', '한강 조망 가능 (프리미엄)', '{"한강조망","리버뷰"}', '{"premium":true,"weight":10}'),
  ('공원뷰', 'view', '공원뷰', '공원 조망·인접', '{"공원근처","공원앞","공원조망"}', '{"weight":10}'),
  ('산뷰', 'view', '산뷰', '산 조망', '{"산조망","산이보이는"}', '{"weight":10}'),
  ('시티뷰', 'view', '시티뷰', '도심·야경 조망', '{"도심조망","야경"}', '{"weight":10}'),
  ('탁트인전망', 'view', '탁트인 전망', '시야 넓고 전망 좋음', '{"탁트인","뷰좋음","전망좋음","오픈뷰","시야넓음"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 19. 주변환경 (environment) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('조용한동네', 'environment', '조용한 동네', '주거 환경 조용함', '{"한적","주택가"}', '{"weight":10}'),
  ('채광좋음', 'environment', '채광 좋음', '햇빛 잘 들어옴', '{"환한","밝은","일조량"}', '{"weight":10}'),
  ('편의시설근처', 'environment', '편의시설 근처', '마트·편의점 가까움', '{"마트","편의점근처","상가근처"}', '{"weight":10}'),
  ('병원근처', 'environment', '병원 근처', '의원·약국 가까움', '{"의원","약국근처"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 20. 보안 (security) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('보안', 'security', '보안', 'CCTV·경비·24시간 관리', '{"CCTV","경비","24시간관리"}', '{"weight":10}'),
  ('무인택배', 'security', '무인택배', '택배함·무인 택배 보관', '{"택배함","택배보관"}', '{"weight":10}'),
  ('경비실', 'security', '경비실', '관리실·관리인 상주', '{"관리실","관리인"}', '{"weight":10}'),
  ('현관보안', 'security', '현관보안', '디지털도어록·번호키', '{"디지털도어록","번호키"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 21. 건물구조 (structure) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('분리형', 'structure', '분리형', '방·거실 분리된 원룸', '{"분리형원룸"}', '{"weight":10}'),
  ('복도식', 'structure', '복도식', '복도 중심 배치 (호텔형)', '{}', '{"weight":5}'),
  ('계단식', 'structure', '계단식', '계단 중심 배치 (프라이버시 좋음)', '{}', '{"weight":5}'),
  ('루프탑', 'structure', '루프탑', '옥상 테라스 사용 가능', '{"옥상테라스","옥상"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 22. 시설/옵션 (facility) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('올수리', 'facility', '올수리', '전체 인테리어 수리 완료', '{"올리","전체수리","새로수리","올리모델링","깔끔하게수리","전면수리","완전수리"}', '{"weight":10}'),
  ('부분수리', 'facility', '부분수리', '도배·장판·욕실 등 일부 수리', '{"일부수리","도배장판","욕실수리"}', '{"weight":10}'),
  ('리모델링', 'facility', '리모델링', '구조 변경 포함 대규모 수리', '{"리모"}', '{"weight":10}'),
  ('풀옵션', 'facility', '풀옵션', '가전·가구 전부 포함', '{"풀옵","가전풀","가구포함","옵션풀","가전제품포함"}', '{"weight":10}'),
  ('신축', 'facility', '신축', '준공 3년 이내 새 건물', '{"새건물"}', '{"weight":10}'),
  ('시스템에어컨', 'facility', '시스템에어컨', '천장형 에어컨 설치', '{"시에","천장형에어컨","천장에어컨","중앙에어컨"}', '{"weight":10}'),
  ('드레스룸', 'facility', '드레스룸', '별도 옷방/수납공간', '{}', '{"weight":10}'),
  ('베란다확장', 'facility', '베란다확장', '베란다를 실내로 확장', '{"베확","발코니확장"}', '{"weight":10}'),
  ('빌트인', 'facility', '빌트인', '붙박이장·빌트인 가구', '{"붙박이"}', '{"weight":10}'),
  ('인덕션', 'facility', '인덕션', '인덕션/전기레인지 설치', '{"전기레인지"}', '{"weight":10}'),
  ('식기세척기', 'facility', '식기세척기', '식기세척기 설치', '{"식세기"}', '{"weight":10}'),
  ('엘리베이터', 'facility', '엘리베이터', '승강기 있음', '{"EV","승강기"}', '{"weight":10}'),
  ('주차가능', 'facility', '주차가능', '주차 공간 있음', '{"주차1대","주차2대","주차무료","주차장","자주식주차","주차1대이상","주차됨","주차OK","차댈곳"}', '{"weight":10}'),
  ('주차편리', 'facility', '주차편리', '주차 여유 있음', '{}', '{"weight":10}'),
  ('깨끗한', 'facility', '깨끗한', '상태 양호·청결', '{"상태좋음","청결"}', '{"weight":10}'),
  ('통풍좋음', 'facility', '통풍 좋음', '환기·통풍 양호', '{}', '{"weight":10}'),
  ('세탁기포함', 'facility', '세탁기 포함', '세탁기 비치', '{"세탁기","세탁","드럼세탁기"}', '{"weight":10}'),
  ('건조기포함', 'facility', '건조기 포함', '건조기 비치', '{"건조기"}', '{"weight":10}'),
  ('파티룸', 'facility', '파티룸', '파티룸 사용 가능', '{}', '{"weight":10}'),
  ('공용시설', 'facility', '공용시설', '피트니스·라운지·커뮤니티', '{"공용라운지","커뮤니티","피트니스","헬스장"}', '{"weight":10}'),
  ('테라스', 'facility', '테라스', '테라스·발코니 공간', '{"발코니"}', '{"weight":10}'),
  ('다락방', 'facility', '다락방', '다락 공간 있음', '{"다락"}', '{"weight":10}'),
  ('방음좋음', 'facility', '방음 좋음', '방음·층간소음 양호', '{"방음","층간소음"}', '{"weight":10}'),
  ('회의실포함', 'facility', '회의실 포함', '공용 회의실 사용 가능 (사무실)', '{}', '{"weight":10}'),
  ('1층상가', 'facility', '1층 상가', '상가 건물 1층 위치', '{}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 23. 금융조건 (finance) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('HUG가능', 'finance', 'HUG 가능', '주택도시보증공사 전세보증보험 가입 가능', '{"허그","안심전세","보증보험","허그가능","전세보증","보증보험OK","보험가능"}', '{"weight":10}'),
  ('무융자', 'finance', '무융자', '선순위 융자 없음, 등기 깨끗', '{"융자없음","등기깨끗","선순위없음"}', '{"weight":10}'),
  ('대출가능', 'finance', '대출 가능', '전세대출·디딤돌·버팀목·신생아특례 가능', '{"전세대출","버팀목","신생아특례","디딤돌"}', '{"weight":10}'),
  ('관리비포함', 'finance', '관리비 포함', '월세에 관리비 포함', '{"관포","관리비없음","관없음"}', '{"weight":10}'),
  ('가격협의', 'price_flex', '가격협의', '네고·가격 조절 가능', '{"네고가능","가격조절","조절가능","급매"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 24. 상가 전용 (commercial) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('전면넓음', 'commercial', '전면 넓음', '상가 전면 폭이 넓어 가시성 좋음', '{"전면","전면광고"}', '{"weight":15}'),
  ('코너자리', 'commercial', '코너자리', '모퉁이 위치, 2면 노출', '{"코너상가","모퉁이"}', '{"weight":15}'),
  ('유동인구많음', 'commercial', '유동인구 많음', '보행자 통행량 많은 입지', '{"유동많음","사람많은"}', '{"weight":15}'),
  ('간판가능', 'commercial', '간판 가능', '대형 간판 설치 가능', '{"대형간판","간판"}', '{"weight":15}'),
  ('권리금없음', 'commercial', '권리금 없음', '권리금 없이 인수 가능', '{"무권리","권리금0"}', '{"weight":15}'),
  ('업종제한없음', 'commercial', '업종 제한 없음', '모든 업종 입점 가능', '{"업종자유","모든업종"}', '{"weight":15}')
on conflict (tag) do nothing;

-- ── 25. 특수조건 (special) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('애견가능', 'special', '애견 가능', '반려동물 입주 허용', '{"반려견가능","강아지OK","강아지가능","동물가능","반려견OK","반려동물","펫","고양이","캣프렌들리"}', '{"weight":10}'),
  ('여성전용', 'special', '여성전용', '여성만 입주 가능', '{"여자전용","여성만","여자만"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ── 26. 부동산 신조어 (neologism) ──
insert into tag_dictionary (tag, category, display, description, synonyms, metadata) values
  ('초품아', 'neologism', '초품아', '초등학교를 품은 아파트 (단지 내 초교)', '{"초등학교품은","단지내초교","초세권"}', '{"weight":10}'),
  ('슬세권', 'neologism', '슬세권', '슬리퍼 신고 갈 수 있는 생활권 (편의시설 가까움)', '{"상권좋은"}', '{"weight":10}'),
  ('런세권', 'neologism', '런세권', '달리기 좋은 환경 (하천변·산책로)', '{"천변길","조깅"}', '{"weight":10}'),
  ('숲세권', 'neologism', '숲세권', '숲·공원 인접한 주거지', '{"숲근처"}', '{"weight":10}'),
  ('맥세권', 'neologism', '맥세권', '맥도날드 인근 (배달 편의 상징)', '{"맥도날드"}', '{"weight":10}'),
  ('스세권', 'neologism', '스세권', '스타벅스 인근 (카페 생활권)', '{"별세권","스타벅스"}', '{"weight":10}'),
  ('몰세권', 'neologism', '몰세권', '대형마트·쇼핑몰 인근', '{"대형마트","쇼핑몰"}', '{"weight":10}'),
  ('쿡세권', 'neologism', '쿡세권', '맛집·먹자골목 인근', '{"맛집많은","먹자골목"}', '{"weight":10}'),
  ('편세권', 'neologism', '편세권', '편의점 가까운 생활권', '{}', '{"weight":10}'),
  ('의세권', 'neologism', '의세권', '대형병원 인근', '{"대형병원"}', '{"weight":10}')
on conflict (tag) do nothing;

-- ═══════════════════════════════════════════════════════════
-- usage_count 동기화 함수 (수동 실행)
-- ═══════════════════════════════════════════════════════════
create or replace function sync_tag_usage_counts()
returns void as $$
begin
  update tag_dictionary td
  set usage_count = coalesce(sub.cnt, 0)
  from (
    select unnest(tags) as tag, count(*) as cnt
    from cards
    where tags is not null
    group by 1
  ) sub
  where td.tag = sub.tag;
end;
$$ language plpgsql;

-- 코멘트
comment on table tag_dictionary is '휙 태그 사전 — 모든 시스템 태그의 의미·동의어·메타데이터 중앙 관리';
comment on column tag_dictionary.tag is '표준 태그명 (PK) — generateTags()가 생성하는 최종 태그';
comment on column tag_dictionary.category is '태그 카테고리 (region_city, trade_type, property_type, price_sale 등)';
comment on column tag_dictionary.synonyms is '이 태그로 변환되는 동의어 목록 (SYNONYM_MAP과 동기화)';
comment on column tag_dictionary.metadata is '카테고리별 추가 정보 (가격: min/max, 지역: city/code, 면적: sqm 등)';
comment on column tag_dictionary.usage_count is '실제 cards 테이블에서 사용 횟수 (sync_tag_usage_counts() 실행 시 갱신)';
