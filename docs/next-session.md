# 다음 세션 할 일 (2026-04-22 이후)

## 세션 시작 멘트
"docs/next-session.md 보고 이어서 해줘"

## 1순위 — 임대단지 404 근본 정리
오늘(2026-04-21) 이안테라디움 주변 단지에 "정릉풍림아이원임대" 링크 → 404 사고. 런타임 방어만 해둠(`danji/app.js` `/임대/` 필터, 커밋 `e590c47a737`). 근본 치료 필요:
1. **빌드 스크립트 찾기** — `build_danji_pages.py` / `build_gu_pages.py` / `build_dong_pages.py` / `build_ranking.py` 존재 확인
2. **nearby_complex 생성·저장 시점에 "임대" 필터** — DB `danji_pages.nearby_complex`에서 임대 제외 (근본)
3. **전국 정적 HTML 재빌드** — 기존 파일에 박힌 임대 링크 제거 (SSR fallback 순간 노출 방지)
4. **dong/gu/ranking에도 동일 필터 확인** — "임대" 포함 단지가 리스트에 있는지 grep로 점검

## 2순위 — 로그인 리다이렉트 전환 (선택)
`index.html:114` 로그인된 중개사 접속 시 `card_generator_v2_auth.html` → `/hub-new/` 전환 여부 결정. 사업 판단.

## 3순위 — 오늘 유지된 것들
- 브라우저 UI E2E (사용자 직접)
- JWT 자동 갱신 관찰 (오늘 회귀에선 정상 작동)
- 공유방 매칭 / 대량 카드 스트레스 / 실거래 연계 (보류)

## 오늘(2026-04-21) 오후 완료
- **매칭 업그레이드 2건**: 소형 15→20평 기준, room 카테고리 호환성(apartment/officetel ≤15평 허용). 75/75 pass + hyunsil 50/50 regression 없음. 커밋(배포 완료).
- **danji CTA → hub-new 전환**: 커밋 `7ca7ccf55a0`
- **임대 nearby 런타임 필터**: 커밋 `e590c47a737`
- 상세: [docs/2026-04-21.md](2026-04-21.md) 후반부

## 금지
- 반복 테스트 과잉 금지 (`feedback_api_cost_waste`)
- 새 기능 금지 (`feedback_stability_first`)
- 대량 페이지 수정은 1개 먼저 → 확인 → 전체 (`feedback_one_page_first`)
- 매칭 Edge Function 수정 시 `npm run deploy:matching` 필수

## 테스트 실행
```bash
node tests/smoke_matching.mjs --file=scenarios_price_range.json --concurrency=3   # 15 가격범위
node tests/smoke_matching.mjs --file=scenarios_realistic.json --concurrency=3     # 10 실전
node tests/smoke_matching.mjs --file=scenarios_hyunsil.json --concurrency=5       # 50 regression
npm run deploy:matching                                                            # 배포 게이트
```
