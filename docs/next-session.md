# 다음 세션

## 세션 시작 멘트
"docs/next-session.md 보고 이어서 해줘" → docs/2026-04-25-evening.md 읽기

## 🔴 다음 세션 최우선 — 생성된 URL 중복 검사
**왜**: 9,833 단지 + 1,402 허브(dong/gu/ranking) URL이 새로 정렬됐는데, 자치구 시 정정 과정에서 같은 슬러그로 충돌하는 단지가 있을 수 있음 (다른 단지가 같은 dong/gu URL 갖거나, 동명 단지 id 충돌 등).

**검사 항목** (전부 0건이어야 통과):
1. **단지 페이지** `officetel/*.html` — 파일명(슬러그) 중복 0건
2. **dong 페이지** `officetel/dong/*.html` — `make_dong_slug` 결과 중복 0건
3. **gu 페이지** `officetel/gu/*.html` — `gu_url_slug` 결과 중복 0건
4. **단지 url 컬럼** vs 실제 파일 — 1:1 대응 (DB url ↔ 빌드 파일)
5. **sitemap 등록 URL** — 같은 loc 중복 등록 0건
6. **단지 id ↔ url 충돌** — 다른 id가 같은 url 가지는 경우 0건

**검사 스크립트 작성**: `verify_url_uniqueness.py` (신규) — 위 6항목 한 번에 검증, 실패 시 어느 슬러그가 누구와 충돌하는지 출력.

## 🟢 2026-04-25 저녁2 완료
- **오피스텔 dong/gu URL 근본 정상화** (깨진 인터널 링크 0건 검증)
- DB 651건 교체 (자치구가 umd 자리에 잘못 들어가 있던 문제):
  - 예) `sgg=고양시, umd=덕양구` → `sgg=고양덕양구, umd=원흥동`
  - 백업: `_umd_fix/dryrun_1777086820.json` (old_sgg/old_umd 보존)
- 빌드 코드 2개 모두 `slug_utils.make_dong_slug` / `gu_url_slug` 사용 — URL 단일 소스
- 9,833 단지 + 1,196 dong + 188 gu + 18 ranking 페이지 재빌드 완료
- 검증: 단지 페이지 9,851건 / 깨진 dong/gu/ranking 링크 0건

### 404 영구 방지 보강
1. `scripts/officetel_sync/safety_guards.py::assert_umd_is_dong` — umd가 *구로 끝나면 stage6 적재 거부 (단위 테스트 통과)
2. `build_officetel_sitemap.py` (신규, 아파트와 분리) — 빌드된 파일 실존 확인 후에만 sitemap 등록
   - `sitemap_officetel.xml` (인덱스)
   - `sitemap_officetel_danji.xml` (9,833)
   - `sitemap_officetel_hubs.xml` (1,402: gu 188 + dong 1,196 + ranking 17 + index 1)
   - 루트 `sitemap.xml`에 항목 자동 추가 완료

## 🟡 미반영 (디자인 확정 후)
- D 디자인 → `build_officetel_pages.py` 정식 통합 (`preview_desktop_designs.py` 오버레이로만 검증)
- og-image 단지별 동적 생성
- modified_time 해시 비교 (매일 신규 데이터 수집 후 변경 시만)
- report-danji Edge Function이 o-prefix 처리하는지 백엔드 검증

## 핵심 파일
- `build_officetel_pages.py` — 본 빌드 (slug_utils 사용 ✅)
- `build_officetel_index_pages.py` — gu/dong/ranking (slug_utils 사용 ✅)
- `build_officetel_sitemap.py` — 오피스텔 전용 sitemap (분리 ✅)
- `slug_utils.py` — `make_dong_slug`, `gu_url_slug` URL 단일 소스
- `scripts/officetel_sync/fix_missing_umd.py` — 자치구 시 단지 정정 도구 (재사용 가능)
- `scripts/officetel_sync/safety_guards.py` — `assert_umd_is_dong` 게이트
- `scripts/officetel_sync/stage6_upload.py` — 게이트 호출

## 절대 건드리지 말 것
- 9,833 officetels.id/slug/url
- danji/style.css (아파트와 공유)
- scripts/officetel_sync/blacklist_mgm.json
- 아파트 sitemap 파일들 (sitemap_seoul/metro/cities/pages.xml)

## 확인 URL
- 자치구 시 단지: https://hwik.kr/officetel/경기-고양시-덕양구-3호선-원흥역-봄오피스텔-o8795601.html
- 자치구 시 dong: https://hwik.kr/officetel/dong/경기-고양-덕양구-원흥동.html
- 자치구 시 gu: https://hwik.kr/officetel/gu/고양덕양구.html
- 단순 시 dong (회귀): https://hwik.kr/officetel/dong/서울-중랑구-망우동.html
- 단순 시 gu (회귀): https://hwik.kr/officetel/gu/중랑구.html
- 오피스텔 sitemap: https://hwik.kr/sitemap_officetel.xml
