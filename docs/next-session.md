# 다음 세션 할 일 (2026-04-21)

## 세션 시작 멘트
"docs/next-session.md 보고 이어서 해줘"

## 오늘(2026-04-20) 완료 — 매칭/검색 시스템 0% → 대부분 복구
- parse-property 74/74 · 손님 25/25 · DB 4/4 · 매칭 E2E 8/8 · locate-card 20/20 · auto-match 역방향 10/10
- search-property 10/15 (치명 2건 수리, 유명동명→구·단지명 부분매치만 남음)
- DB 저장 4경로 일관화 (confirmSave/fiSaveAll/registerClient/saveClientEdit)
- 🚨 fiSaveAll id NULL 위반 (일괄 저장 100% 실패 상태)
- 🚨 match_notifications UNIQUE 제약 추가 (알림 저장 0% 상태)
- 🚨 auto-match pgvector 문자열 파싱 (유사도 NaN → 매칭 0% 상태)
- 🚨 auto-match card select에 wanted_trade_type 누락 (손님→매물 방향 전면 실패)
- 🚨 search-property tags jsonb에 postgres array 문법 (SQL 태그 검색 400)
- 커밋 `6dfa9d5→3b0f0ea→71b843a→27764cc→066d31c→adfaafd→531c195` (7개) 배포 완료

## 1순위 — hub-new 브라우저 E2E 확인 (사용자)
자동 테스트로 서버 전 경로 통과 확인. 이제 실제 브라우저 UI 확인 필요.
- https://hwik.kr/hub-new/# 접속
- 매물 1건 등록 (아파트) → "🏢 단지 매칭됨" 토스트
- 상가 1건 등록 → area·관리비·권리금 표시 확인
- 손님 1건 등록 → 직전 매물과 자동 매칭되어 손님 알림 뜨는지
- 일괄 등록 1회 (저장 성공 여부만 확인)

## 2순위 — 매칭 알림 이관 데이터 복구
- 어제까지 match_notifications 비어있음. 기존 매물·손님으로 일괄 매칭 재실행 스크립트 필요
- 또는 활성 중개사만 대상으로 하룻밤 배치 돌리기

## 3순위 — 보류
- search-property 남은 5건 해결
  - "홍대/잠실/대치" 같은 유명동명→구 자동 매핑 (현재 agent 본인구 fallback)
  - 단지명 부분 매치 ("래미안"→"래미안 삼성동" 포함 매물)
  - tags에 price_number 태그와 별도로 숫자 직접 필터 확인
- wanted_conditions / wanted_categories 매칭 활용 (현재 저장만 됨)
- auto-match THRESHOLD 조정 (현재 0.25, 통과했으니 유지 가능)
- 공유방 매물 auto-match 누락
- 단지 매칭 정확도 게이트 강화

## 금지
- 새 기능 금지 (`feedback_stability_first.md`)
- 대량 페이지 일괄 수정 금지 (`feedback_one_page_first.md`)
- 지인 중개사 초대 금지 (브라우저 UI 3회 연속 에러 0% 전까지)
