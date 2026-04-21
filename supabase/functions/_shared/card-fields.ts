// 매칭 시스템 공통 select 필드
// auto-match, match-properties, room-share-match 3개 Edge Function이
// cards 테이블에서 select할 때 사용. drift 방지를 위해 이 파일만 수정.

// 손님/매물 공통 기본 필드
export const MATCH_BASE =
  'id, property, agent_id, embedding, price_number, deposit, monthly_rent, lat, lng, kapt_code, tags, private_note, search_text';

// 손님 카드 전용 — wanted_* / 태그 제약 / 입주시기 / 상태
export const MATCH_CLIENT_EXTRA =
  'wanted_trade_type, wanted_categories, wanted_conditions, required_tags, excluded_tags, move_in_date, client_status';

// 매물 카드 전용
export const MATCH_PROPERTY_EXTRA =
  'trade_status, agent_comment, photos, created_at';

// 조합
export const CLIENT_SELECT = [MATCH_BASE, MATCH_CLIENT_EXTRA].join(', ');
export const PROPERTY_SELECT = [MATCH_BASE, MATCH_PROPERTY_EXTRA].join(', ');

// 방향 결정 전의 본인 카드 (손님/매물 양쪽 대응) — auto-match에서 사용
export const SELF_SELECT = [MATCH_BASE, MATCH_CLIENT_EXTRA, 'trade_status'].join(', ');
