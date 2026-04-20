# 다음 세션 할 일 (2026-04-22)

## 세션 시작 멘트
"docs/next-session.md 보고 이어서 해줘"

## 오늘(2026-04-21) 완료
- 매칭 시스템 E2E 테스트 인프라 구축 — **210/210 PASS**
- Edge Function 3개 drift 차단 (_shared/card-fields.ts)
- 진짜 버그 4건 수정 (월세 DB 우선, rawText 누락, 범위 문법, select 필드)
- 배포 게이트 완성 (`npm run deploy:matching`)
- [docs/matching-contract.md](matching-contract.md) · [docs/2026-04-21.md](2026-04-21.md)

## 1순위 — 테스트 인프라 확장 (나머지 5개 축)
현재 210개는 "손님→매물 auto-match" 주로 커버. 아직 안 된 것:
1. **locate-card 연계** — 좌표 반영 매칭 (거리 보너스 +0.25/+0.20/+0.12/+0.05)
2. **공유방 매칭(room-share-match)** — 공유방 멤버·손님 통합
3. **태그 기반(required_tags / excluded_tags)** — 필수·제외 태그
4. **embedding 엣지** — null·길이 불일치·NaN
5. **match-properties** — 손님 기준 매물 검색 직접 테스트

## 2순위 — 브라우저 UI E2E 확인 (사용자)
테스트는 HTTP 계층 증명. UI 버튼·폼은 사람이 직접:
- https://hwik.kr/hub-new/# 매물 1건 등록 → "🏢 단지 매칭됨" 토스트 뜨는지
- 손님 1건 등록 → 매칭 알림이 UI에 떠오르는지
- 일괄 등록 1회

## 3순위 — 보류
- wanted_conditions 매칭 활용 (저장만 되고 검색에 활용 적음)
- auto-match THRESHOLD 튜닝 (현재 0.25)
- 단지 매칭 정확도 게이트

## 금지
- 새 기능 금지 (`feedback_stability_first.md`)
- 대량 페이지 일괄 수정 금지 (`feedback_one_page_first.md`)
- 매칭 관련 Edge Function 수정 시 `npm run deploy:matching` 필수 (210/210 통과 확인)
- 지인 중개사 초대 금지 (브라우저 UI 3회 연속 에러 0% 전까지)

## 테스트 실행 방법
```bash
# 1회 셋업: tests/README.md 참고해서 .env.test에 JWT·AGENT_ID
# 테스트만
node tests/smoke_matching.mjs --concurrency=5

# 테스트 통과하면 배포까지
npm run deploy:matching

# 특정 시나리오만
node tests/smoke_matching.mjs --only=S01,G198
```

## JWT 만료 주의
JWT는 1시간 만료. 테스트 돌릴 때 401 나오면 브라우저에서 재추출:
```js
copy(JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith('sb-')&&k.endsWith('auth-token')))).access_token)
```
