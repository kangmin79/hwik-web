-- 단지 페이지 테이블
CREATE TABLE IF NOT EXISTS danji_pages (
  id text PRIMARY KEY,
  complex_name text NOT NULL,
  location text,
  address text,
  lat numeric,
  lng numeric,
  total_units integer,
  build_year integer,
  categories jsonb,
  recent_trade jsonb,
  all_time_high jsonb,
  jeonse_rate numeric,
  nearby_subway jsonb,
  nearby_school jsonb,
  nearby_complex jsonb,
  active_listings jsonb,
  seo_text text,
  updated_at timestamp DEFAULT now()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_danji_pages_location ON danji_pages (location);
CREATE INDEX IF NOT EXISTS idx_danji_pages_updated ON danji_pages (updated_at DESC);

-- RLS 활성화 (읽기 전용 공개)
ALTER TABLE danji_pages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "danji_pages_public_read" ON danji_pages;
CREATE POLICY "danji_pages_public_read" ON danji_pages
  FOR SELECT USING (true);

-- 래미안 마포리버웰 샘플 데이터
INSERT INTO danji_pages (
  id, complex_name, location, address, lat, lng,
  total_units, build_year, categories,
  recent_trade, all_time_high, jeonse_rate,
  nearby_subway, nearby_school, nearby_complex,
  active_listings, seo_text
) VALUES (
  'raemian-mapo-riverwell',
  '래미안 마포리버웰',
  '마포구 신수동',
  '서울특별시 마포구 강변북로2나길 15',
  37.5387, 126.9530,
  1101, 2024,
  '["59A","59B","84A","84B","114"]'::jsonb,
  '{
    "59A": {"price": 131000, "floor": 12, "date": "2026-02", "type": "매매"},
    "84A": {"price": 175000, "floor": 8, "date": "2026-03", "type": "매매"},
    "114": {"price": 230000, "floor": 15, "date": "2026-01", "type": "매매"},
    "59A_jeonse": {"price": 72000, "floor": 5, "date": "2026-02", "type": "전세"},
    "84A_jeonse": {"price": 95000, "floor": 10, "date": "2026-03", "type": "전세"}
  }'::jsonb,
  '{
    "59A": {"price": 135000, "date": "2025-11"},
    "84A": {"price": 182000, "date": "2025-10"},
    "114": {"price": 240000, "date": "2025-09"}
  }'::jsonb,
  54.9,
  '[
    {"name": "대흥역", "line": "6호선", "distance": 350},
    {"name": "공덕역", "line": "5호선/6호선/경의중앙선/공항철도", "distance": 650}
  ]'::jsonb,
  '[
    {"name": "신수초등학교", "distance": 200, "type": "초등"},
    {"name": "마포중학교", "distance": 400, "type": "중학"},
    {"name": "서울여고", "distance": 550, "type": "고등"}
  ]'::jsonb,
  '[
    {"id": "mapo-raemian-purgio", "name": "래미안푸르지오", "location": "마포구 아현동", "price_84": 180000},
    {"id": "mapo-presian", "name": "마포프레스티지자이", "location": "마포구 염리동", "price_84": 172000},
    {"id": "mapo-xi", "name": "마포자이", "location": "마포구 신수동", "price_84": 140000}
  ]'::jsonb,
  '[]'::jsonb,
  '래미안 마포리버웰은 서울특별시 마포구 신수동에 위치한 2024년 준공 아파트입니다. 총 1,101세대 규모로, 6호선 대흥역 도보 5분 거리의 역세권 단지입니다. 59㎡, 84㎡, 114㎡ 등 다양한 평형대를 갖추고 있으며, 한강 조망이 가능한 세대가 포함되어 있습니다. 신수초등학교가 도보 3분 거리에 있어 학군도 우수합니다. 마포구 대표 신축 아파트로, 래미안푸르지오, 마포프레스티지자이 등 주변 대단지와 함께 마포구 핵심 주거지를 형성하고 있습니다.'
) ON CONFLICT (id) DO UPDATE SET
  complex_name = EXCLUDED.complex_name,
  recent_trade = EXCLUDED.recent_trade,
  all_time_high = EXCLUDED.all_time_high,
  jeonse_rate = EXCLUDED.jeonse_rate,
  updated_at = now();
