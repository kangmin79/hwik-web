# 다음 세션 (2026-04-27)

## 세션 시작 멘트
"docs/next-session.md 보고 이어서 해줘" → 이 문서 + docs/2026-04-26-d-design-deploy.md 읽기

---

## 🔴 1순위 — dong / gu / ranking 페이지 D 디자인 적용

### 배경
- 4/26 단지 페이지(13K) D 디자인 운영 배포 완료
- dong / gu / ranking 페이지는 OLD 디자인 그대로 → **단지 페이지와 시각 톤 불일치**
- GSC 70% PC 이용자 기준으로 dong/gu/ranking 도 D 적용 필요

### 대상 파일
- `build_dong_pages.py` (1,523개 동 페이지)
- `build_gu_pages.py` (232개 구 페이지)
- `build_ranking_pages.py` (서울/인천/경기/전체 4개 + 카테고리)

### 참고 — 이미 적용된 D 디자인 자산
- `build_d_design.py` — 단지 페이지 D 헬퍼 함수 17개
- `danji/style-d.css` — D CSS 18.6KB (헤더/카드/탭/메트릭/footer 등)
- `danji/app.js` — applyDDesign(d) + 11개 D 변환 함수

### 안전 전략 (어기지 말 것)
1. 단지 페이지처럼 환경변수 게이트 (`USE_D_DESIGN=1`) 로 OLD/D 분기
2. ONE_DONG_ID / ONE_GU_ID / ONE_RANKING_ID 같은 미리보기 환경변수 먼저 추가
3. 1개 페이지 빌드 → 사용자 시각 OK → 전체 → 배포
4. cloaking 회피: SSR fallback ≈ hydrated DOM 텍스트 일치
5. URL/canonical/robots 절대 건드리지 말 것

### 작업 순서 (제안)
1. dong 페이지 1개 D 적용 → 헬리오시티 동 (서울 송파구 가락동) 미리보기 → 사용자 OK
2. gu 페이지 1개 D 적용 → 송파구 미리보기 → 사용자 OK
3. ranking 페이지 1개 D 적용 → 서울 매매가 ranking → 사용자 OK
4. dong 1,523 + gu 232 + ranking N 전체 빌드
5. SSR fingerprint 검증 (랜덤 5개씩)
6. commit + push
7. sync-trades.yml 의 build_dong/gu/ranking 호출에도 USE_D_DESIGN=1 추가 (자동 빌드 보호)

### 주의사항
- dong / gu / ranking 의 hydrated DOM 패턴이 단지 페이지와 다를 수 있음 — 각 페이지의 SPA 구조 먼저 확인
- 오피스텔 D 적용은 4/26 새벽 작업분에 build_officetel_index_pages.py 의 gu 만 로컬 미리보기 OK 받은 상태 → 그것도 운영 push 결정 필요

---

## 🟡 잔여 — 4/27 KST 03시 첫 cron 발화 결과 점검 (오피스텔 일일 동기화)
1. 메일: `[휙][오피스텔][OK or FAIL] 2026-04-27 일일 동기화`
2. Actions 로그: https://github.com/kangmin79/hwik-web/actions/workflows/officetel-daily.yml
3. DB 변동: `officetel_trades` 신규 row, `officetels.trade_count` 변화

---

## 🟢 4/26 완료 (참고)
- 단지 페이지 D 디자인 13K 운영 배포 (commit 5842ee0fd61)
- sync-trades.yml 에 USE_D_DESIGN=1 추가 (commit 0c90620a177)
- 운영 URL 3개 D fingerprint 4/4 검증 완료
- 18,608 페이지 D 적용 / 색인 6,000개+ 보유 / 매일 ~200/일 색인 중

상세: docs/2026-04-26-d-design-deploy.md

---

## 🔵 추후 작업 후보 (우선순위 낮음, 별도 세션)
- nearby_complex N=5→10 확장 (파이프라인 변경, 큰 작업)
- danji_pages.parking 헬리오시티 등 NULL 보강 (건축물대장 연동)
- 오피스텔 gu/dong/ranking 운영 push (4/26 새벽 작업분)

---

## 🛠️ 참고 명령
- 단지 빌드 (D): `USE_D_DESIGN=1 python build_danji_pages.py`
- 단지 1개: `USE_D_DESIGN=1 ONE_DANJI_ID=a10025850 python build_danji_pages.py`
- 미리보기 서버: `python -m http.server 8765`
- 운영 URL 확인: https://hwik.kr/danji/...
