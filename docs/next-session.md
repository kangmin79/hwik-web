# 다음 세션 할 일 (2026-04-21)

## 세션 시작 멘트
"docs/next-session.md 보고 이어서 해줘"

## 오늘(2026-04-20) 완료 — 매칭 시스템 0% → 100% 복구
- parse-property 74케이스 통과 (가격 반올림·null문자열·백100·반지하·한글가격파서)
- DB 저장 4경로 일관화 (confirmSave/fiSaveAll/registerClient/saveClientEdit)
- 🚨 fiSaveAll id NULL 제약 위반 수정 (일괄 저장 100% 실패 상태였음)
- 🚨 match_notifications UNIQUE 제약 추가 (알림 저장 0% 상태였음)
- 🚨 auto-match pgvector 문자열 파싱 (벡터 유사도 NaN → 매칭 0% 상태였음)
- 손님 파싱 보강 (location/category 필수 해제, 반전세, wanted_categories 폴백)
- 손님 매칭 E2E 8/8 통과 (locate-card → auto-match → match_notifications)
- 커밋 `066d31cc530` 배포 완료

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
- wanted_conditions / wanted_categories 매칭 활용 (현재 저장만 됨)
- auto-match THRESHOLD 조정 (현재 0.25, E2E 8/8 통과했으니 유지 가능)
- 공유방 매물 auto-match 누락 (`session_20260419_evening.md` 계승)
- 단지 매칭 정확도 게이트 강화

## 금지
- 새 기능 금지 (`feedback_stability_first.md`)
- 대량 페이지 일괄 수정 금지 (`feedback_one_page_first.md`)
- 지인 중개사 초대 금지 (브라우저 UI 3회 연속 에러 0% 전까지)
