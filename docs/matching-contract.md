# 매칭 시스템 필드 계약

손님↔매물 매칭 3개 Edge Function이 읽고 쓰는 필드의 단일 출처.

## 0. 원칙

**필드를 바꿀 때는 `supabase/functions/_shared/card-fields.ts` 한 파일만 수정한다.**
3개 Edge Function(auto-match / match-properties / room-share-match)은 이 파일에서 상수만 import 한다. 개별 Edge Function에서 select 문자열을 직접 쓰는 것을 금지한다.

## 1. 참여 함수

| 함수 | 용도 | self select | target select |
|------|------|------------|--------------|
| auto-match | 신규 카드 저장 시 역방향 일괄 매칭 | `SELF_SELECT` | `PROPERTY_SELECT` or `CLIENT_SELECT` |
| match-properties | 손님 카드 기준 매물 검색 | `CLIENT_SELECT` | `PROPERTY_SELECT` |
| room-share-match | 공유방 매물을 방 멤버 손님과 매칭 | `PROPERTY_SELECT` | `CLIENT_SELECT` |

## 2. 필드 상수 (card-fields.ts)

### MATCH_BASE (공통)
`id, property, agent_id, embedding, price_number, deposit, monthly_rent, lat, lng, kapt_code, tags, private_note, search_text`

### MATCH_CLIENT_EXTRA (손님 전용)
`wanted_trade_type, wanted_categories, wanted_conditions, required_tags, excluded_tags, move_in_date`

### MATCH_PROPERTY_EXTRA (매물 전용)
`trade_status, agent_comment, photos, created_at`

### 조합
- `CLIENT_SELECT = MATCH_BASE + MATCH_CLIENT_EXTRA`
- `PROPERTY_SELECT = MATCH_BASE + MATCH_PROPERTY_EXTRA`
- `SELF_SELECT = MATCH_BASE + MATCH_CLIENT_EXTRA + trade_status` (방향 결정 전용)

## 3. 필드별 역할

| 필드 | 타입 | 읽는 쪽 | 의미 |
|------|------|---------|------|
| property | jsonb | 모든 함수 | type/category/price/location/features 등 표시용 |
| embedding | vector | 모든 함수 | 벡터 유사도. pgvector는 문자열로 반환되므로 `parseEmb` 필수 |
| price_number | bigint | 매물(자신 가격) / 손님(조건 안 씀) | 매매·전세 매물의 실제 가격 |
| deposit / monthly_rent | bigint | 매물(자신) / 손님(wanted_conditions로도 저장) | 월세 거래 조건 |
| lat / lng | float8 | 모든 함수 | haversineDistance로 거리 보너스 계산 |
| kapt_code | text | 모든 함수 | 동일 단지 매칭 보너스 (+0.20) |
| tags | jsonb[] | 모든 함수 | SQL 1차 필터(`cs`) + 후필터 |
| private_note.memo | text | filterMatch 내 allText | 가격/지역/면적 텍스트 파싱 원천 |
| search_text | text | 검색·재현용 | 임베딩 원문 |
| **wanted_trade_type** | text | 손님→매물 매칭 | 단일 거래유형. wanted_conditions가 우선 |
| **wanted_categories** | text[] | 손님→매물 매칭 | 복수 카테고리 OR |
| **wanted_conditions** | jsonb[] | match-properties | 거래유형별 복수 조건 {trade_type, minPrice, maxPrice, deposit, monthly} |
| **required_tags** | text[] | 모든 함수 | 손님이 모두 보유해야 하는 태그 |
| **excluded_tags** | text[] | 모든 함수 | 손님이 한 개라도 있으면 제외 |
| **move_in_date** | date | 점수 가중치 (미구현) | 입주 시기 |

## 4. 쓰는 쪽 (프론트엔드)

| 진입점 | 파일 | 저장 필드 |
|--------|------|----------|
| 매물 단건 등록 | hub-new/index.html `confirmSave` | property, price_number, deposit, monthly_rent, lat, lng, tags, kapt_code, search_text, embedding |
| 매물 일괄 등록 | hub-new/index.html `fiSaveAll` | ↑ 동일 + id |
| 손님 등록 | hub-new/index.html `registerClient` | property, wanted_trade_type, wanted_categories, wanted_conditions, required_tags, excluded_tags, tags, price_number, deposit, monthly_rent, embedding, search_text |
| 손님 수정 | hub-new/index.html `saveClientEdit` | ↑ 동일 |

**계약 위반 체크**: 저장 경로가 위 필드 중 하나라도 빼먹으면 매칭이 조용히 실패한다. parse-property 응답을 insert에 `...r` 스프레드로 넘기지 말고 명시 매핑하라.

## 5. 점수 상한

auto-match / room-share-match 유사도 최대:
- cosine similarity: 1.0
- 카테고리 일치: +0.10
- 거리 ≤0.5km: +0.25
- 동일 단지(kapt_code): +0.20
- **최대 1.55 / THRESHOLD 0.25**

match-properties threshold: 0.15 (이중 필터링이라 낮게)

## 6. 알림 저장

`match_notifications(agent_id, card_id, client_card_id)` UNIQUE 제약.
모든 함수는 `upsert({onConflict: 'agent_id,card_id,client_card_id', ignoreDuplicates: true})` 사용.

## 7. 수정 규칙

1. **필드 추가**: `card-fields.ts`에만 추가, 3개 함수는 자동 반영
2. **신규 매칭 함수**: 반드시 이 파일에서 import (새 select 문자열 금지)
3. **프론트 저장 경로 변경**: 이 문서의 4번 표를 먼저 업데이트
4. **배포 전 필수**: 3개 함수가 실제로 새 필드를 쓰는지 grep 확인
