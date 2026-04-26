# 다음 세션

## 세션 시작 멘트
"docs/next-session.md 보고 이어서 해줘" → 이 문서 + docs/2026-04-26-d-design-deploy.md 읽기

---

## 🟢 4/26 완료 — 단지 페이지 D 디자인 13K 운영 배포
- 18,608개 단지 페이지 D 디자인 적용 + git push
- 시각: 헤더 location-section, 단지명 인디고, 단지 소개 dl, 시세 요약 토글, footer, FAQ 보강, CTA 제거
- SEO: 클로킹 안전(SSR≈hydrated), JSON-LD FAQPage 16 Q&A, structured `<dl>`
- 모바일: 미디어쿼리 min-width 1px + max-width 767px 보정 (헤더 1열 스택)
- GSC 70% PC 에 맞는 디자인 변경

상세: docs/2026-04-26-d-design-deploy.md

---

## 🟡 잔여 — 4/27 KST 03시 첫 cron 발화 결과 점검 (오피스텔 일일 동기화)
1. 메일: `[휙][오피스텔][OK or FAIL] 2026-04-27 일일 동기화`
2. Actions 로그: https://github.com/kangmin79/hwik-web/actions/workflows/officetel-daily.yml
3. DB 변동: `officetel_trades` 신규 row, `officetels.trade_count` 변화

---

## 🔵 다음 작업 후보 (우선순위 순)

### 1) 단지 페이지 배포 검증 (gp 전파 후)
- 운영 URL https://hwik.kr/danji/... 5~10개 시각 확인
- GSC `URL 검사` 로 D 디자인 색인 정상 확인
- Core Web Vitals 변화 모니터 (LCP/CLS)
- 1~2주 후 GSC `Devices` 리포트 → CTR/Position 변화 측정

### 2) nearby_complex N=5→10 확장 (선택)
- 파이프라인 스크립트 위치 파악 + 변경 + 13K 단지 nearby 재계산
- 작업량: 큼 (별도 세션)

### 3) danji_pages.parking 헬리오시티 등 NULL 보강
- apartments 테이블 또는 건축물대장에서 보강
- 작업량: 중

### 4) dong / gu / ranking 페이지 D 디자인 적용 검토
- 단지 페이지만 D 적용했음. dong/gu/ranking 은 OLD 그대로
- 사용자 결정 필요 (B2B2C 트래픽 vs SEO 가치 vs 작업량 비교)

### 5) gu 강남구 오피스텔 페이지 운영 push (4/26 새벽 작업분)
- 로컬 미리보기 OK 받음
- dong/ranking 동일 톤 적용 후 일괄 운영 반영 예정 (사용자 콜)

---

## 🛠️ 참고 명령
- 단지 페이지 빌드 (D): `USE_D_DESIGN=1 python build_danji_pages.py`
- 단지 1개 미리보기: `USE_D_DESIGN=1 ONE_DANJI_ID=a10025850 python build_danji_pages.py`
- 미리보기 서버: `python -m http.server 8765`
- D 미리보기: http://localhost:8765/danji_test/design-d-preview-a10025850.html
- 정식 (D): http://localhost:8765/danji/서울-송파구-가락동-헬리오시티아파트-a10025850.html
