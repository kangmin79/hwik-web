# 다음 세션 (2026-04-28~)

## 세션 시작 멘트
"docs/next-session.md 보고 이어서 해줘 — 4/28 새벽 빌드 결과 검증부터"

## 🔴 1순위 — 4/28 새벽 빌드 결과 검증 (필수 첫 작업)

**4/27 저녁에 안전장치를 다 박았으니, 4/28 KST 01시 새벽 빌드 결과만 확인하면 됨. 안전장치는 d0bbc12f9ba 커밋의 verify_all.py D 디자인 마커 게이트(Phase 2).**

### 4/28 오전에 확인할 것

1. **메일 확인** — `bgtrfvcdewsx77@gmail.com` 에 빌드 결과 메일 자동 발송됨
   - 제목 `[휙] 2026-04-28 자동 빌드 완료 — ALL PASS ✓` → 정상
   - 제목 `[휙][FAIL] 2026-04-28 자동 빌드 실패` → Phase 2에서 D 마커 누락 감지된 것. 로그·diff 보고 원인 파악

2. **D 디자인 보존 실측 (PC 라이트)**
   - https://hwik.kr/gu/강남구.html
   - https://hwik.kr/dong/서울-강남구-대치동.html
   - https://hwik.kr/ranking/seoul-price.html
   - 베이지 #F0EEE6 배경, 720px 흰 카드, Pretendard, 인디고 액센트 유지되는지

3. **단지 title 일괄 적용 확인**
   - https://hwik.kr/danji/서울-송파구-신천동-잠실르엘-a10020230.html (어제 미리 빌드한 5개 중 하나)
   - 새벽 빌드된 임의의 다른 단지: title이 `XX 시세·실거래가 (전용 N㎡ X억 Y천) · 구 동 | 휙` 형태인지
   - **5개 미리 빌드 단지 목록 (비교 기준)**: 잠실르엘(a10020230), 대치1차현대(a10024799), 효창파크푸르지오(a14074101), 구리역롯데캐슬시그니처(a10020188), 황금동태왕아너스(a70604001)

### 만약 FAIL이면
- D 디자인 마커 누락 — 이건 Phase 2가 빌드 결과를 차단한 것. push 안 됨. production 영향 없음.
- 빌더 코드 회귀 가능성 → `git log --oneline -- build_*_pages.py` 로 이상 커밋 확인
- 빌더 옛 디자인으로 회귀했으면 git revert 또는 핫픽스

## 🟢 4/27 저녁 완료 (참고)

### 3개 커밋 추가
1. `d0bbc12f9ba` — verify_all.py D 디자인 마커 회귀 게이트 (dong/gu/ranking)
   - Phase 2에서 `Pretendard` / `hero-left` / `#F0EEE6` / `#4338ca` 4종 검증
   - 하나라도 빠지면 FAIL → push 차단

2. `48b037c1f75` — ranking.html `?gu=<한글>` redirect 처리
   - GSC 옛 SPA URL `/ranking.html?gu=마포구&type=jeonse` 같은 케이스 → `/gu/<name>` 정확 안내
   - 클릭 1·노출 10 짜리 작은 케이스지만 정확도 ↑

3. `97c001192c2` — 단지 페이지 title 평형·매매가 추가
   - Before: `잠실르엘 실거래가 시세 · 송파구 신천동 | 휙`
   - After : `잠실르엘 시세·실거래가 (전용 74㎡ 34억 2천) · 송파구 신천동 | 휙`
   - GSC 데스크톱 CTR 0.16% 개선 시도 (단지명+실거래 검색의도 직접 매칭)
   - 5개 단지 미리 빌드 + 18,603개는 4/28 새벽 자동 빌드에서 일괄

### 4/27 GSC 분석 결과 (메모)
- 클릭 94 / 노출 22,000+ / CTR 0.43% / 평균순위 9.29 (지난 3개월)
- 데스크톱 CTR 0.16% (모바일 1.61%의 1/10) — 가장 큰 손실
- 단지명 정확 검색은 CTR 25%+ 잘 나옴, 정보형 검색("국토부 실거래가...")은 CTR 0
- 4/26 D 디자인 + 4/27 새 title 효과는 5/3~5/10에 GSC 다시 받아 측정

## 🟢 4/27 낮 완료 사항 (참고)

### dong/gu/ranking D 디자인 적용 (커밋 `d5aeebf659a` + `f3dead9c79c`)
- gu 231개 + dong 1,522개 + ranking 72개 = **1,825개 페이지** 통합 적용
- 모바일 다크 + PC ≥768px 라이트 (베이지 #F0EEE6, 720px 흰 카드, Pretendard, 인디고 액센트)
- 1위 hero 카드 + 2~ 컴팩트, 자연어 섹션 제목 ("강남구에서 가장 비싼 아파트는?")
- JSON-LD 강화 (Organization + CollectionPage + AdministrativeArea + FAQPage + ItemList + BreadcrumbList)
- 환경변수: `ONE_GU`, `ONE_DONG_SLUG`, `ONE_RANK_SLUG` (단일 페이지 빌드)

### 기타
- 오피스텔 일일 cron 정상화 (sync 17/17 + build 4단계 + commit/push)
- sitemap percent-encoded 통일 (`dbf5380fe6e`)
- GSC `sitemap_officetel.xml` 제출 완료

## 🟡 2순위 이후 (1순위 검증 끝나면)

1. **17개 untracked 마이그레이션** 일괄 commit (`docs/2026-04-27-officetel-daily-debug.md` 81~108줄)
2. **세종 P3 매칭 0%** — sgg_cd 매핑 / 블랙리스트
3. **nearby_complex N=5→10 확장**
4. **danji_pages.parking 헬리오시티 등 NULL 보강**
5. **danji_pages.active_listings writer 없음** — 플라이휠 끊김 (메모리 1순위 후보)
6. **TODO 메모리 점검** (cardgen_preview, telegram_chat_logs 등)
7. **단지 페이지(/danji/)에도 같은 D 디자인 통일 검토** (이미 적용됐는지 확인)

## 📅 별도 트리거 (시간이 답을 주는 작업)

- **5/3~5/10**: GSC 다시 받기 → 데스크톱 CTR + 단지 페이지 클릭률 변화 측정
  - 0.16% → 0.5%+ 오르면 D 디자인 + 새 title 효과 검증 완료
  - 그대로면 단지 외관 사진 추가·title 추가 최적화 검토
- **6~12주 후**: Bing favicon 캐시 갱신 (자연 대기, 수동 작업 불필요)

## 🛠️ 참고
- main 최신: `97c001192c2` (단지 title 평형·매매가)
- GSC: hwik.kr 등록·sitemap.xml + sitemap_officetel.xml 제출 완료
- cron: KST 매일 01시 (sync_trades.yml 기준, UTC 16:00 전일) — 4/28 오전이 첫 검증
- 자동 빌드 결과 메일: `bgtrfvcdewsx77@gmail.com`
